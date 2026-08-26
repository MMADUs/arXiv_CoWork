import type { FormEvent, KeyboardEvent } from "react";
import { Send, Square } from "lucide-react";

export function MessageComposer({
  draft,
  error,
  isGenerating,
  onDraftChange,
  onSend,
  onStop,
}: {
  draft: string;
  error: string | null;
  isGenerating: boolean;
  onDraftChange: (value: string) => void;
  onSend: (content: string) => void;
  onStop: () => void;
}) {
  function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
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
        <div className="composer-hint">Shift + Enter for a new line</div>
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
