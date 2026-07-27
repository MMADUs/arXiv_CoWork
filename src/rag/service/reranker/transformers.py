# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from rag.config import TransformersRerankerSettings
from rag.service.reranker.interface import (
    RerankCandidate,
    RerankResult,
    RerankerProvider,
)

_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    "based on the Query and the Instruct provided. Note that the answer can "
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_INSTRUCTION = "Given a search query, retrieve relevant passages that answer the query"


class TransformersReranker(RerankerProvider):
    provider_name = "huggingface_transformers"

    def __init__(self, settings: TransformersRerankerSettings) -> None:
        self.device = settings.device
        self.model_name = settings.model_name
        self.max_length = settings.max_length

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, padding_side="left"
        )
        self.model = (
            AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16,
            )
            .to(settings.device)
            .eval()
        )

        self.token_false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.token_true_id = self.tokenizer.convert_tokens_to_ids("yes")

        self._prefix_tokens = self.tokenizer.encode(_PREFIX, add_special_tokens=False)
        self._suffix_tokens = self.tokenizer.encode(_SUFFIX, add_special_tokens=False)

    async def rerank(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_k: int,
    ) -> RerankResult:
        if not chunks:
            return RerankResult(
                provider=self.provider_name,
                model_name=self.model_name,
                latency_ms=None,
                reranked_chunks=[],
            )

        pairs = [
            f"<Instruct>: {_INSTRUCTION}\n<Query>: {query}\n<Document>: {chunk.get('chunk_text', '')}"
            for chunk in chunks
        ]

        scores = self._score(pairs)

        scored = [
            {"chunk": chunk, "score": score, "original_rank": i + 1}
            for i, (chunk, score) in enumerate(zip(chunks, scores))
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)

        selected = scored[:top_k]

        reranked_candidate: list[RerankCandidate] = []

        for rank, item in enumerate(selected, start=1):
            chunk = dict(item["chunk"])
            chunk["reranker_score"] = item["score"]
            chunk["reranker_rank"] = rank

            reranked_candidate.append(
                RerankCandidate(
                    chunk_id=item["chunk"]["chunk_id"],
                    chunk=chunk,
                    original_rank=item["original_rank"],
                    original_score=item["chunk"].get("score"),
                    reranker_score=item["score"],
                    final_rank=rank,
                )
            )

        return RerankResult(
            provider=self.provider_name,
            model_name=self.model_name,
            latency_ms=None,
            reranked_chunks=reranked_candidate,
        )

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
