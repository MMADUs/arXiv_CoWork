# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from time import perf_counter

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from rag.config import TransformersRerankerSettings
from rag.service.elasticsearch.config import SearchHit
from rag.service.reranker.reranker_interface import (
    RerankCandidate,
    RerankResult,
    RerankerProvider,
)
from rag.service.reranker.reranker_exceptions import (
    RerankerModelLoadError,
    RerankerProviderError,
    RerankerResponseError,
    RerankerValidationError,
)

_PREFIX = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n"
    "<|im_start|>user\n"
)

_SUFFIX = "<|im_end|>\n" "<|im_start|>assistant\n" "<think>\n\n</think>\n\n"

_INSTRUCTION = "Given a search query, retrieve relevant passages that answer the query"


def _format_rerank_pair(query: str, document: str) -> str:
    return "\n".join(
        [
            f"<Instruct>: {_INSTRUCTION}",
            f"<Query>: {query}",
            f"<Document>: {document}",
        ]
    )


class HFTransformersReranker(RerankerProvider):
    """
    HFTransformersReranker reranks search hit candidates by relevance,
    through `rerank()` method.
    """

    provider_name = "huggingface_transformers"

    def __init__(self, settings: TransformersRerankerSettings) -> None:
        self.device = self._resolve_device(settings.device)
        self.model_name = settings.model_name
        self.max_length = settings.max_length

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, padding_side="left"
            )
            self.model = (
                AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16,
                )
                .to(self.device)
                .eval()
            )

        except Exception as error:
            raise RerankerModelLoadError(
                f"Failed to load reranker model: {self.model_name}"
            ) from error

        self.token_false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.token_true_id = self.tokenizer.convert_tokens_to_ids("yes")

        if not isinstance(self.token_false_id, int) or not isinstance(
            self.token_true_id, int
        ):
            raise RerankerResponseError(
                "Reranker tokenizer does not contain required yes/no tokens"
            )

        self._prefix_tokens = self.tokenizer.encode(_PREFIX, add_special_tokens=False)
        self._suffix_tokens = self.tokenizer.encode(_SUFFIX, add_special_tokens=False)

    async def rerank(
        self,
        query: str,
        chunks: list[SearchHit],
        top_k: int,
    ) -> RerankResult:
        """
        Rerank search hits by scoring each chunk against the query.

        Args:
            query:
                user search query used to judge chunk relevance
            chunks:
                candidate search hits to rerank
            top_k:
                maximum number of reranked candidates to return

        Raises:
            RerankerValidationError:
                If the query is empty or top_k is not greater than 0
            RerankerProviderError:
                If the reranker model fails while scoring candidates
            RerankerResponseError:
                If the reranker score output is invalid
        """
        if not query.strip():
            raise RerankerValidationError("Cannot rerank with an empty query")

        if top_k <= 0:
            raise RerankerValidationError("top_k must be greater than 0")

        if not chunks:
            return RerankResult(
                provider=self.provider_name,
                model_name=self.model_name,
                reranked_candidates=[],
                latency_ms=None,
            )

        started_at = perf_counter()

        pairs = [_format_rerank_pair(query, chunk.chunk_text) for chunk in chunks]

        try:
            scores = self._score(pairs)

        except RerankerResponseError:
            raise

        except Exception as error:
            raise RerankerProviderError(
                "Failed to score reranker candidates"
            ) from error

        if len(scores) != len(chunks):
            raise RerankerResponseError(
                "Reranker score count did not match candidate count"
            )

        scored = [
            {
                "chunk": chunk,
                "score": score,
                "original_rank": i + 1,
            }
            for i, (chunk, score) in enumerate(zip(chunks, scores))
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)

        selected = scored[:top_k]

        reranked_candidates: list[RerankCandidate] = []

        for rank, item in enumerate(selected, start=1):
            chunk = item["chunk"]

            reranked_candidates.append(
                RerankCandidate(
                    chunk_id=chunk.chunk_id,
                    chunk=chunk,
                    original_rank=item["original_rank"],
                    original_score=chunk.score,
                    reranker_rank=rank,
                    reranker_score=item["score"],
                )
            )

        return RerankResult(
            provider=self.provider_name,
            model_name=self.model_name,
            reranked_candidates=reranked_candidates,
            latency_ms=(perf_counter() - started_at) * 1000,
        )

    def _resolve_device(self, configured_device: str) -> str:
        if configured_device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"

        return configured_device

    @torch.no_grad()
    def _score(self, pairs: list[str]) -> list[float]:
        inputs = self.tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=self.max_length
            - len(self._prefix_tokens)
            - len(self._suffix_tokens),
        )

        for i, ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = self._prefix_tokens + ids + self._suffix_tokens

        inputs = self.tokenizer.pad(
            inputs, padding=True, return_tensors="pt", max_length=self.max_length
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        logits = self.model(**inputs).logits[:, -1, :]

        true_vec = logits[:, self.token_true_id]
        false_vec = logits[:, self.token_false_id]

        stacked = torch.stack([false_vec, true_vec], dim=1)

        probs = torch.nn.functional.log_softmax(stacked, dim=1)

        return probs[:, 1].exp().tolist()
