import { SlidersHorizontal, RotateCcw } from "lucide-react";
import type { RetrievalConfig, RetrievalMode } from "../model/types";

const retrievalModes: Array<{ value: RetrievalMode; label: string }> = [
  { value: "hybrid", label: "Hybrid" },
  { value: "vector", label: "Vector" },
  { value: "bm25", label: "BM25" },
];

export function RetrievalSettings({
  config,
  open,
  onOpenChange,
  onUpdate,
  onReset,
}: {
  config: RetrievalConfig;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdate: (update: Partial<RetrievalConfig>) => void;
  onReset: () => void;
}) {
  return (
    <div className="retrieval-settings">
      <button
        className={`icon-button ${open ? "active" : ""}`}
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-label="Retrieval settings"
        aria-expanded={open}
        title="Retrieval settings"
      >
        <SlidersHorizontal size={18} />
      </button>

      {open ? (
        <div className="retrieval-popover">
          <div className="retrieval-popover-header">
            <strong>Retrieval</strong>
            <button
              className="icon-button compact"
              type="button"
              onClick={onReset}
              aria-label="Reset retrieval settings"
              title="Reset retrieval settings"
            >
              <RotateCcw size={15} />
            </button>
          </div>

          <div className="retrieval-field">
            <span>Mode</span>
            <div className="segmented-control" aria-label="Retrieval mode">
              {retrievalModes.map((mode) => (
                <button
                  key={mode.value}
                  type="button"
                  className={
                    config.retrieval_mode === mode.value ? "active" : ""
                  }
                  onClick={() => onUpdate({ retrieval_mode: mode.value })}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          <label className="retrieval-field">
            <span>Top K</span>
            <input
              type="number"
              min={1}
              max={50}
              value={config.top_k}
              onChange={(event) =>
                onUpdate({ top_k: Number.parseInt(event.target.value, 10) })
              }
            />
          </label>

          <label className="retrieval-field">
            <span>Candidate pool</span>
            <input
              type="number"
              min={1}
              max={500}
              value={config.candidate_pool_size}
              onChange={(event) =>
                onUpdate({
                  candidate_pool_size: Number.parseInt(event.target.value, 10),
                })
              }
            />
          </label>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={config.use_reranker}
              onChange={(event) =>
                onUpdate({ use_reranker: event.target.checked })
              }
            />
            <span>Use reranker</span>
          </label>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={config.include_highlights}
              onChange={(event) =>
                onUpdate({ include_highlights: event.target.checked })
              }
            />
            <span>Include highlights</span>
          </label>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={config.latest_first}
              onChange={(event) =>
                onUpdate({ latest_first: event.target.checked })
              }
            />
            <span>Latest first</span>
          </label>
        </div>
      ) : null}
    </div>
  );
}
