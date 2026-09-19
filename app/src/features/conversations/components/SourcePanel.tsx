import { useEffect, useState } from "react";
import {
  Archive,
  ChevronDown,
  ChevronRight,
  FileText,
  LoaderCircle,
  Search,
  X,
} from "lucide-react";
import { getMessageSourceChunks } from "../api/conversations";
import type {
  ConversationMessage,
  SourceBlock,
  SourceChunk,
} from "../model/types";

export function SourcePanel({
  message,
  onClose,
}: {
  message: ConversationMessage | null;
  onClose: () => void;
}) {
  const citations = message?.metadata?.citations ?? [];
  const sources = message?.metadata?.sources ?? [];
  const [expandedPaperId, setExpandedPaperId] = useState<string | null>(null);
  const [chunkCache, setChunkCache] = useState<Record<string, SourceChunk[]>>({});
  const [loadingPaperId, setLoadingPaperId] = useState<string | null>(null);
  const [chunkError, setChunkError] = useState<string | null>(null);
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

  useEffect(() => {
    setExpandedPaperId(null);
    setChunkCache({});
    setLoadingPaperId(null);
    setChunkError(null);
  }, [message?.message_id]);

  async function toggleSource(source: SourceBlock) {
    const paperId = source.paper_id;

    if (!message || !paperId) return;

    if (expandedPaperId === paperId) {
      setExpandedPaperId(null);
      return;
    }

    setExpandedPaperId(paperId);
    setChunkError(null);

    if (chunkCache[paperId]) return;

    setLoadingPaperId(paperId);

    try {
      const response = await getMessageSourceChunks({
        roomId: message.room_id,
        messageId: message.message_id,
        paperId,
      });
      setChunkCache((current) => ({
        ...current,
        [paperId]: response.chunks,
      }));
    } catch {
      setChunkError("Could not load retrieved chunks for this source.");
    } finally {
      setLoadingPaperId(null);
    }
  }

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
              expanded={Boolean(
                source.paper_id && source.paper_id === expandedPaperId,
              )}
              chunks={source.paper_id ? chunkCache[source.paper_id] : undefined}
              loading={source.paper_id === loadingPaperId}
              error={
                source.paper_id && source.paper_id === expandedPaperId
                  ? chunkError
                  : null
              }
              onToggle={() => toggleSource(source)}
            />
          ))}
        </div>
      )}
    </aside>
  );
}

function SourceCard({
  source,
  expanded,
  chunks,
  loading,
  error,
  onToggle,
}: {
  source: SourceBlock;
  expanded: boolean;
  chunks?: SourceChunk[];
  loading: boolean;
  error: string | null;
  onToggle: () => void;
}) {
  return (
    <article className="source-card">
      <button
        className="source-card-button"
        type="button"
        onClick={onToggle}
        disabled={!source.paper_id}
        aria-expanded={expanded}
      >
        <div className="source-card-top">
          <span>Paper {source.paper_source_number ?? "?"}</span>
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
        <span className="source-expand-hint">
          {expanded ? "Hide retrieved chunks" : "Show retrieved chunks"}
          <ChevronDown size={15} />
        </span>
      </button>

      {expanded ? (
        <RetrievedChunks chunks={chunks} loading={loading} error={error} />
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

function RetrievedChunks({
  chunks,
  loading,
  error,
}: {
  chunks?: SourceChunk[];
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return (
      <div className="source-chunk-state">
        <LoaderCircle size={15} />
        Loading retrieved chunks...
      </div>
    );
  }

  if (error) {
    return <div className="source-chunk-state error">{error}</div>;
  }

  if (!chunks?.length) {
    return (
      <div className="source-chunk-state">
        No retrieved chunk text is available for this source.
      </div>
    );
  }

  return (
    <div className="source-chunks">
      {chunks.map((chunk) => (
        <article className="source-chunk" key={chunk.chunk_id}>
          <div className="source-chunk-top">
            <span>[Source {chunk.source_number ?? "?"}]</span>
            <span>Chunk {chunk.chunk_index}</span>
            {typeof chunk.score === "number" ? (
              <span>Score {chunk.score.toFixed(3)}</span>
            ) : null}
          </div>
          {chunk.section_title ? <h4>{chunk.section_title}</h4> : null}
          {chunk.highlights.length ? (
            <div className="highlights">
              {chunk.highlights.slice(0, 2).map((highlight, index) => (
                <blockquote key={`${chunk.chunk_id}-${index}`}>
                  {highlight}
                </blockquote>
              ))}
            </div>
          ) : null}
          <p>{chunk.text}</p>
        </article>
      ))}
    </div>
  );
}
