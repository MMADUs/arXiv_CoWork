import { useEffect, useState } from "react";
import type { RetrievalConfig, RetrievalMode } from "../model/types";

const STORAGE_KEY = "arxiv-cowork.retrieval-config";

export const DEFAULT_RETRIEVAL_CONFIG: RetrievalConfig = {
  retrieval_mode: "hybrid",
  top_k: 8,
  candidate_pool_size: 50,
  use_reranker: false,
  include_highlights: false,
  latest_first: false,
};

export function useRetrievalConfig() {
  const [config, setConfig] = useState<RetrievalConfig>(() =>
    readStoredConfig(),
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch {
      // Retrieval still works with in-memory settings if persistence is unavailable.
    }
  }, [config]);

  function updateConfig(update: Partial<RetrievalConfig>) {
    setConfig((current) => sanitizeConfig({ ...current, ...update }));
  }

  function resetConfig() {
    setConfig(DEFAULT_RETRIEVAL_CONFIG);
  }

  return {
    retrievalConfig: config,
    updateRetrievalConfig: updateConfig,
    resetRetrievalConfig: resetConfig,
  };
}

function readStoredConfig(): RetrievalConfig {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_RETRIEVAL_CONFIG;

    return sanitizeConfig({
      ...DEFAULT_RETRIEVAL_CONFIG,
      ...JSON.parse(stored),
    });
  } catch {
    return DEFAULT_RETRIEVAL_CONFIG;
  }
}

function sanitizeConfig(value: Partial<RetrievalConfig>): RetrievalConfig {
  const topK = clampInteger(value.top_k, 1, 50, DEFAULT_RETRIEVAL_CONFIG.top_k);
  const candidatePoolSize = Math.max(
    topK,
    clampInteger(
      value.candidate_pool_size,
      1,
      500,
      DEFAULT_RETRIEVAL_CONFIG.candidate_pool_size,
    ),
  );

  return {
    retrieval_mode: sanitizeRetrievalMode(value.retrieval_mode),
    top_k: topK,
    candidate_pool_size: candidatePoolSize,
    use_reranker: value.use_reranker === true,
    include_highlights: value.include_highlights === true,
    latest_first: value.latest_first === true,
  };
}

function sanitizeRetrievalMode(value: unknown): RetrievalMode {
  if (value === "bm25" || value === "vector" || value === "hybrid") {
    return value;
  }

  return DEFAULT_RETRIEVAL_CONFIG.retrieval_mode;
}

function clampInteger(
  value: unknown,
  min: number,
  max: number,
  fallback: number,
) {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number.parseInt(value, 10)
        : Number.NaN;

  if (!Number.isFinite(parsed)) return fallback;

  return Math.min(max, Math.max(min, Math.round(parsed)));
}
