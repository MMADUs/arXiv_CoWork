import { ExternalLink, Loader2, Play, RefreshCw, Trash2, X } from "lucide-react";
import { StatusChip } from "./StatusChip";
import type { FullPaper } from "../model/types";

export function PaperDetailDrawer({
  paper,
  loading,
  actionPending,
  onClose,
  onIndex,
  onReindex,
  onReprocess,
  onDeleteIndex,
  onDeleteMetadata,
}: {
  paper: FullPaper | null;
  loading: boolean;
  actionPending: boolean;
  onClose: () => void;
  onIndex: () => void;
  onReindex: () => void;
  onReprocess: () => void;
  onDeleteIndex: () => void;
  onDeleteMetadata: () => void;
}) {
  const actions = paper ? paperDetailActions(paper) : null;

  return (
    <aside className="library-drawer">
      <div className="library-drawer-header">
        <div>
          <p className="eyebrow">Library</p>
          <h2>Paper details</h2>
        </div>
        <button
          className="icon-button drawer-close"
          type="button"
          onClick={onClose}
          aria-label="Close paper details"
        >
          <X size={18} />
        </button>
      </div>

      {!paper ? (
        <div className="library-drawer-empty">
          Select a paper to inspect its indexing state.
        </div>
      ) : (
        <div className="library-drawer-body">
          {loading ? (
            <div className="drawer-loading">
              <Loader2 size={17} className="spin-icon" />
              Refreshing detail
            </div>
          ) : null}

          <section className="paper-detail-section">
            <h3>{paper.metadata.title}</h3>
            <p>{paper.metadata.authors.join(", ")}</p>
            <div className="paper-category-row">
              {paper.metadata.categories.map((category) => (
                <span key={category}>{category}</span>
              ))}
            </div>
            <a href={paper.metadata.pdf_url} target="_blank" rel="noreferrer">
              Open arXiv PDF
              <ExternalLink size={14} />
            </a>
          </section>

          <section className="paper-detail-section">
            <h4>Pipeline</h4>
            <div className="detail-status-grid">
              <StatusChip label="PDF" value={paper.status.ingestion_status} />
              <StatusChip label="Parse" value={paper.status.parser_status} />
              <StatusChip label="Chunk" value={paper.status.chunking_status} />
              <StatusChip label="Index" value={paper.status.indexing_status} />
            </div>
          </section>

          <section className="paper-detail-section">
            <h4>Artifacts</h4>
            <dl className="artifact-list">
              <div>
                <dt>arXiv ID</dt>
                <dd>{paper.arxiv_id}</dd>
              </div>
              <div>
                <dt>PDF object</dt>
                <dd>{paper.artifacts.pdf_object_key || "Not stored"}</dd>
              </div>
              <div>
                <dt>Parsed JSON</dt>
                <dd>{paper.artifacts.parsed_json_object_key || "Not stored"}</dd>
              </div>
              <div>
                <dt>Parser</dt>
                <dd>{paper.artifacts.parser_name || "Not parsed"}</dd>
              </div>
            </dl>
          </section>

          <section className="paper-detail-section">
            <h4>Actions</h4>
            {actions?.note ? (
              <p className="detail-action-note">{actions.note}</p>
            ) : null}
            <div className="library-action-grid">
              {actions?.canIndex ? (
                <button
                  className="library-primary-button"
                  type="button"
                  onClick={onIndex}
                  disabled={actionPending}
                >
                  <Play size={15} />
                  Index
                </button>
              ) : null}
              {actions?.canReindex ? (
                <button
                  className="library-secondary-button"
                  type="button"
                  onClick={onReindex}
                  disabled={actionPending}
                >
                  <RefreshCw size={15} />
                  Reindex
                </button>
              ) : null}
              {actions?.canRetryPipeline ? (
                <button
                  className={
                    actions.canIndex || actions.canReindex
                      ? "library-secondary-button"
                      : "library-primary-button"
                  }
                  type="button"
                  onClick={onReprocess}
                  disabled={actionPending}
                  title="Retry parsing, chunking, and indexing from the stored PDF"
                >
                  <RefreshCw size={15} />
                  Retry pipeline
                </button>
              ) : null}
              {actions?.canDeleteIndex ? (
                <button
                  className="library-danger-button"
                  type="button"
                  onClick={onDeleteIndex}
                  disabled={actionPending}
                >
                  <Trash2 size={15} />
                  Delete index
                </button>
              ) : null}
              <button
                className="library-danger-button strong"
                type="button"
                onClick={onDeleteMetadata}
                disabled={actionPending || !actions?.canDeletePaper}
                title={
                  actions?.canDeletePaper
                    ? "Delete this paper and stored artifacts"
                    : "Wait until the active pipeline step finishes"
                }
              >
                Delete paper
              </button>
            </div>
          </section>

          <section className="paper-detail-section">
            <h4>Errors</h4>
            <ErrorList paper={paper} />
          </section>

          <section className="paper-detail-section">
            <h4>Abstract</h4>
            <p>{paper.metadata.abstract}</p>
          </section>
        </div>
      )}
    </aside>
  );
}

function paperDetailActions(paper: FullPaper) {
  const ingestionStatus = paper.status.ingestion_status;
  const parserStatus = paper.status.parser_status;
  const chunkingStatus = paper.status.chunking_status;
  const indexingStatus = paper.status.indexing_status;
  const hasPdf = Boolean(paper.artifacts.pdf_object_key);
  const isActive =
    ingestionStatus === "pdf_downloading" ||
    parserStatus === "parsing" ||
    chunkingStatus === "chunking" ||
    indexingStatus === "indexing";
  const isIndexed = indexingStatus === "indexed";
  const hasFailure =
    parserStatus === "failed" ||
    chunkingStatus === "failed" ||
    indexingStatus === "failed";
  const hasIndexCleanupTarget =
    isIndexed ||
    indexingStatus === "failed" ||
    chunkingStatus === "chunked" ||
    paper.errors.chunk_errors.length > 0;
  const canIndex =
    hasPdf &&
    !isActive &&
    !isIndexed &&
    !hasFailure &&
    chunkingStatus !== "no_chunks";
  const canReindex = hasPdf && !isActive && isIndexed;
  const canRetryPipeline = hasPdf && !isActive && hasFailure;
  const canDeleteIndex = !isActive && hasIndexCleanupTarget;
  const canDeletePaper = !isActive;

  return {
    canIndex,
    canReindex,
    canRetryPipeline,
    canDeleteIndex,
    canDeletePaper,
    note: actionNote({
      hasPdf,
      isActive,
      isIndexed,
      hasFailure,
      chunkingStatus,
      canIndex,
      canReindex,
      canRetryPipeline,
    }),
  };
}

function actionNote({
  hasPdf,
  isActive,
  isIndexed,
  hasFailure,
  chunkingStatus,
  canIndex,
  canReindex,
  canRetryPipeline,
}: {
  hasPdf: boolean;
  isActive: boolean;
  isIndexed: boolean;
  hasFailure: boolean;
  chunkingStatus: string;
  canIndex: boolean;
  canReindex: boolean;
  canRetryPipeline: boolean;
}) {
  if (canIndex || canReindex || canRetryPipeline) return null;
  if (isActive) return "A pipeline step is running. Actions unlock when it finishes.";
  if (!hasPdf) return "PDF is not stored yet, so indexing actions are unavailable.";
  if (chunkingStatus === "no_chunks") return "This paper has no chunks to index.";
  if (isIndexed) return null;
  if (hasFailure) return null;
  return null;
}

function ErrorList({ paper }: { paper: FullPaper }) {
  const errors = [
    ["PDF", paper.errors.pdf_download_error],
    ["Parser", paper.errors.parser_error],
    ["Chunking", paper.errors.chunking_error],
    ["Indexing", paper.errors.indexing_error],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  if (errors.length === 0 && paper.errors.chunk_errors.length === 0) {
    return <p className="muted-copy">No recorded errors.</p>;
  }

  return (
    <div className="error-stack">
      {errors.map(([stage, message]) => (
        <div className="error-box" key={stage}>
          <strong>{stage}</strong>
          <span>{message}</span>
        </div>
      ))}
      {paper.errors.chunk_errors.map((error) => (
        <div
          className="error-box"
          key={`${error.stage}-${error.message}-${error.count}`}
        >
          <strong>
            {error.stage} · {error.count}
          </strong>
          <span>{error.message}</span>
        </div>
      ))}
    </div>
  );
}
