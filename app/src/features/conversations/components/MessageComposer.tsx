import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Filter, Send, Square, X } from "lucide-react";
import type { MessageRetrievalFilterDraft } from "../model/types";

export function MessageComposer({
  draft,
  error,
  isGenerating,
  messageFilters,
  messageFiltersActive,
  onDraftChange,
  onMessageFiltersChange,
  onClearMessageFilters,
  onSend,
  onStop,
}: {
  draft: string;
  error: string | null;
  isGenerating: boolean;
  messageFilters: MessageRetrievalFilterDraft;
  messageFiltersActive: boolean;
  onDraftChange: (value: string) => void;
  onMessageFiltersChange: (update: Partial<MessageRetrievalFilterDraft>) => void;
  onClearMessageFilters: () => void;
  onSend: (content: string) => void;
  onStop: () => void;
}) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!filtersOpen) return;

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && filtersRef.current?.contains(target)) {
        return;
      }

      setFiltersOpen(false);
    }

    function handleEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        setFiltersOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [filtersOpen]);

  function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
    setFiltersOpen(false);
    onSend(draft);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about your indexed papers..."
        rows={3}
      />
      {error ? <p className="composer-error">{error}</p> : null}
      <div className="composer-footer">
        <div className="composer-left-tools">
          <div className="message-filter-menu" ref={filtersRef}>
            <button
              type="button"
              className={`composer-filter-button ${
                messageFiltersActive ? "active" : ""
              }`}
              onClick={() => setFiltersOpen((current) => !current)}
              title="Message filters"
              aria-label="Message filters"
              aria-expanded={filtersOpen}
            >
              <Filter size={14} />
              <span>Filters</span>
            </button>
            {filtersOpen ? (
              <div
                className="message-filter-popover"
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                  }
                }}
              >
                <div className="message-filter-header">
                  <strong>Message filters</strong>
                  <div className="message-filter-actions">
                    {messageFiltersActive ? (
                      <button
                        className="text-button"
                        type="button"
                        onClick={onClearMessageFilters}
                      >
                        Clear
                      </button>
                    ) : null}
                    <button
                      className="icon-button compact"
                      type="button"
                      onClick={() => setFiltersOpen(false)}
                      aria-label="Close message filters"
                      title="Close message filters"
                    >
                      <X size={15} />
                    </button>
                  </div>
                </div>

                <label className="composer-filter-field">
                  <span>Paper ID</span>
                  <input
                    type="text"
                    value={messageFilters.paper_id}
                    onChange={(event) =>
                      onMessageFiltersChange({ paper_id: event.target.value })
                    }
                    placeholder="UUID"
                  />
                </label>

                <label className="composer-filter-field">
                  <span>Categories</span>
                  <input
                    type="text"
                    value={messageFilters.categories}
                    onChange={(event) =>
                      onMessageFiltersChange({ categories: event.target.value })
                    }
                    placeholder="cs.CL, cs.AI"
                  />
                </label>

                <div className="composer-filter-grid">
                  <label className="composer-filter-field">
                    <span>Published from</span>
                    <input
                      type="date"
                      value={messageFilters.published_from}
                      onChange={(event) =>
                        onMessageFiltersChange({
                          published_from: event.target.value,
                        })
                      }
                    />
                  </label>

                  <label className="composer-filter-field">
                    <span>Published to</span>
                    <input
                      type="date"
                      value={messageFilters.published_to}
                      onChange={(event) =>
                        onMessageFiltersChange({
                          published_to: event.target.value,
                        })
                      }
                    />
                  </label>
                </div>
              </div>
            ) : null}
          </div>
          <div className="composer-hint">Shift + Enter for a new line</div>
        </div>
        {isGenerating ? (
          <button
            className="send-button stop"
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop generating"
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            className="send-button"
            type="submit"
            disabled={!draft.trim()}
            aria-label="Send message"
            title="Send message"
          >
            <Send size={16} />
          </button>
        )}
      </div>
    </form>
  );
}
