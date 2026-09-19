import type { FormEvent } from "react";
import {
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import type {
  IndexPendingPapersPayload,
  IndexPreviewResponse,
  LibraryFilter,
  PaperSummaryResponse,
} from "../model/types";

export type BulkIndexDraft = Required<IndexPendingPapersPayload>;

export function LibraryToolbar({
  summary,
  filter,
  query,
  parserStatus,
  chunkingStatus,
  indexingStatus,
  page,
  pages,
  pageSize,
  total,
  refreshing,
  bulkOpen,
  bulkDraft,
  preview,
  previewLoading,
  indexingPending,
  bulkDisabled,
  onFilterChange,
  onQueryChange,
  onParserStatusChange,
  onChunkingStatusChange,
  onIndexingStatusChange,
  onRefresh,
  onPageSizeChange,
  onPreviousPage,
  onNextPage,
  onBulkOpenChange,
  onBulkDraftChange,
  onBulkSubmit,
}: {
  summary?: PaperSummaryResponse;
  filter: LibraryFilter;
  query: string;
  parserStatus: string;
  chunkingStatus: string;
  indexingStatus: string;
  page: number;
  pages: number;
  pageSize: number;
  total: number;
  refreshing: boolean;
  bulkOpen: boolean;
  bulkDraft: BulkIndexDraft;
  preview?: IndexPreviewResponse;
  previewLoading: boolean;
  indexingPending: boolean;
  bulkDisabled: boolean;
  onFilterChange: (filter: LibraryFilter) => void;
  onQueryChange: (query: string) => void;
  onParserStatusChange: (status: string) => void;
  onChunkingStatusChange: (status: string) => void;
  onIndexingStatusChange: (status: string) => void;
  onRefresh: () => void;
  onPageSizeChange: (pageSize: number) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onBulkOpenChange: (open: boolean) => void;
  onBulkDraftChange: (draft: BulkIndexDraft) => void;
  onBulkSubmit: (event: FormEvent) => void;
}) {
  return (
    <section className="library-toolbar" aria-label="Library controls">
      {summary ? (
        <div className="library-summary-grid">
          <SummaryItem label="Total" value={summary.total} />
          <SummaryItem label="Indexed" value={summary.indexed} />
          <SummaryItem label="Pending" value={summary.pending_indexing} />
          <SummaryItem label="Processing" value={summary.processing} />
          <SummaryItem label="Failed" value={summary.failed} />
          <SummaryItem label="Missing PDF" value={summary.missing_pdf} />
        </div>
      ) : null}

      <div className="library-toolbar-row">
        <div className="segmented-control library-filter-tabs">
          <button
            className={filter === "all" ? "active" : ""}
            type="button"
            onClick={() => onFilterChange("all")}
          >
            All
          </button>
          <button
            className={filter === "indexed" ? "active" : ""}
            type="button"
            onClick={() => onFilterChange("indexed")}
          >
            Indexed
          </button>
          <button
            className={filter === "pending" ? "active" : ""}
            type="button"
            onClick={() => onFilterChange("pending")}
          >
            Pending
          </button>
          <button
            className={filter === "indexing" ? "active" : ""}
            type="button"
            onClick={() => onFilterChange("indexing")}
          >
            Indexing
          </button>
          <button
            className={filter === "failed" ? "active" : ""}
            type="button"
            onClick={() => onFilterChange("failed")}
          >
            Failed
          </button>
        </div>

        <div className="library-toolbar-actions">
          <button
            className="icon-button"
            type="button"
            onClick={onRefresh}
            aria-label="Refresh library"
            title="Refresh library"
          >
            <RefreshCw size={17} className={refreshing ? "spin-icon" : ""} />
          </button>
          <button
            className={`library-secondary-button ${bulkOpen ? "active" : ""}`}
            type="button"
            onClick={() => onBulkOpenChange(!bulkOpen)}
          >
            <SlidersHorizontal size={16} />
            Index pending
          </button>
        </div>
      </div>

      <div className="library-filter-row">
        <label className="library-search-field">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search title or arXiv ID"
          />
        </label>
        <StatusSelect
          label="Parser"
          value={parserStatus}
          options={["pending", "parsing", "parsed", "failed"]}
          onChange={onParserStatusChange}
        />
        <StatusSelect
          label="Chunking"
          value={chunkingStatus}
          options={["pending", "chunking", "chunked", "no_chunks", "failed"]}
          onChange={onChunkingStatusChange}
        />
        <StatusSelect
          label="Indexing"
          value={indexingStatus}
          options={["pending", "indexing", "indexed", "failed"]}
          onChange={onIndexingStatusChange}
        />
      </div>

      {bulkOpen ? (
        <form className="bulk-index-panel" onSubmit={onBulkSubmit}>
          <div className="bulk-index-grid">
            <label>
              <span>Limit</span>
              <input
                type="number"
                min={1}
                max={500}
                value={bulkDraft.limit}
                onChange={(event) =>
                  onBulkDraftChange({
                    ...bulkDraft,
                    limit: event.target.valueAsNumber || 1,
                  })
                }
              />
            </label>
            <label>
              <span>Batch size</span>
              <input
                type="number"
                min={1}
                max={500}
                value={bulkDraft.batch_size}
                onChange={(event) =>
                  onBulkDraftChange({
                    ...bulkDraft,
                    batch_size: event.target.valueAsNumber || 1,
                  })
                }
              />
            </label>
          </div>

          <div className="bulk-toggle-grid">
            <label>
              <input
                type="checkbox"
                checked={bulkDraft.include_failed_chunks}
                onChange={(event) =>
                  onBulkDraftChange({
                    ...bulkDraft,
                    include_failed_chunks: event.target.checked,
                  })
                }
              />
              Include failed
            </label>
            <label>
              <input
                type="checkbox"
                checked={bulkDraft.force_parse}
                onChange={(event) =>
                  onBulkDraftChange({
                    ...bulkDraft,
                    force_parse: event.target.checked,
                  })
                }
              />
              Force parse
            </label>
            <label>
              <input
                type="checkbox"
                checked={bulkDraft.force_chunk}
                onChange={(event) =>
                  onBulkDraftChange({
                    ...bulkDraft,
                    force_chunk: event.target.checked,
                  })
                }
              />
              Force chunk
            </label>
            <label>
              <input
                type="checkbox"
                checked={bulkDraft.force_reindex}
                onChange={(event) =>
                  onBulkDraftChange({
                    ...bulkDraft,
                    force_reindex: event.target.checked,
                  })
                }
              />
              Force reindex
            </label>
          </div>

          <button
            className="library-primary-button"
            type="submit"
            disabled={indexingPending || bulkDisabled}
          >
            {indexingPending ? "Queueing..." : "Queue indexing"}
          </button>
          <p className="bulk-preview">
            {previewLoading
              ? "Checking pending papers..."
              : preview
                ? `${preview.requested} papers match this bulk request.`
                : "Open preview unavailable."}
          </p>
        </form>
      ) : null}

      <div className="library-pagination">
        <span>
          {pageWindowLabel(total, page, pageSize)}
          {pages > 0 ? ` · page ${page} of ${pages}` : ""}
        </span>
        <div>
          <label className="library-page-size">
            <span>Rows</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </label>
          <button
            className="icon-button compact"
            type="button"
            onClick={onPreviousPage}
            disabled={page <= 1}
            aria-label="Previous page"
            title="Previous page"
          >
            <ChevronLeft size={17} />
          </button>
          <button
            className="icon-button compact"
            type="button"
            onClick={onNextPage}
            disabled={pages === 0 || page >= pages}
            aria-label="Next page"
            title="Next page"
          >
            <ChevronRight size={17} />
          </button>
        </div>
      </div>
    </section>
  );
}

function pageWindowLabel(total: number, page: number, pageSize: number) {
  if (total === 0) return "No papers";
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return `${start}-${end} of ${total} papers`;
}

function SummaryItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="library-summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="library-status-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Any</option>
        {options.map((option) => (
          <option value={option} key={option}>
            {option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}
