import { Archive, ChevronRight, FileText, Search, X } from "lucide-react";
import type { ConversationMessage, SourceBlock } from "../model/types";

export function SourcePanel({
  message,
  onClose,
}: {
  message: ConversationMessage | null;
  onClose: () => void;
}) {
  const citations = message?.metadata?.citations ?? [];
  const sources = message?.metadata?.sources ?? [];
  const blocks: SourceBlock[] =
    sources.length > 0
      ? sources
      : citations.map((citation) => ({
          paper_source_number: citation.source_number,
          paper_id: citation.paper_id,
          arxiv_id: citation.arxiv_id,
          title: citation.title,
          pdf_url: citation.pdf_url,
          highlights: citation.highlights,
          citation_numbers: citation.source_number
            ? [citation.source_number]
            : [],
        }));

  return (
    <aside className="source-panel">
      <div className="source-header">
        <div>
          <p className="eyebrow">Evidence</p>
          <h2>Sources</h2>
        </div>
        <button
          className="icon-button drawer-close"
          type="button"
          onClick={onClose}
          aria-label="Close sources"
        >
          <X size={18} />
        </button>
        <Archive className="source-header-icon" size={19} />
      </div>

      {!message ? (
        <div className="source-empty">
          <Search size={24} />
          <p>Select an assistant answer to inspect its source blocks.</p>
        </div>
      ) : blocks.length === 0 ? (
        <div className="source-empty">
          <FileText size={24} />
          <p>No citations are attached to this message yet.</p>
        </div>
      ) : (
        <div className="source-list">
          {blocks.map((source, index) => (
            <SourceCard
              source={source}
              key={`${source.paper_id ?? source.title}-${index}`}
            />
          ))}
        </div>
      )}
    </aside>
  );
}

function SourceCard({ source }: { source: SourceBlock }) {
  return (
    <article className="source-card">
      <div className="source-card-top">
        <span>Source {source.paper_source_number ?? "?"}</span>
        {source.arxiv_id ? <span>{source.arxiv_id}</span> : null}
      </div>
      <h3>{source.title || "Untitled source"}</h3>
      {source.authors?.length ? (
        <p>{source.authors.slice(0, 3).join(", ")}</p>
      ) : null}
      {source.categories?.length ? (
        <div className="tag-row">
          {source.categories.slice(0, 4).map((category) => (
            <span key={category}>{category}</span>
          ))}
        </div>
      ) : null}
      {source.highlights?.length ? (
        <div className="highlights">
          {source.highlights.slice(0, 3).map((highlight, index) => (
            <blockquote key={`${highlight}-${index}`}>{highlight}</blockquote>
          ))}
        </div>
      ) : null}
      {source.pdf_url ? (
        <a href={source.pdf_url} target="_blank" rel="noreferrer">
          Open PDF
          <ChevronRight size={15} />
        </a>
      ) : null}
    </article>
  );
}
