import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { BookOpen, MessageSquareText, Moon, Search, Sun } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  deleteLibraryPaperIndex,
  deleteLibraryPaperMetadata,
  getLibrarySummary,
  getLibraryPaper,
  indexLibraryPaper,
  indexPendingLibraryPapers,
  listLibraryPapers,
  previewPendingLibraryPapers,
} from "../features/library/api/papers";
import {
  LibraryToolbar,
  type BulkIndexDraft,
} from "../features/library/components/LibraryToolbar";
import { PaperDetailDrawer } from "../features/library/components/PaperDetailDrawer";
import { PaperTable } from "../features/library/components/PaperTable";
import { libraryKeys } from "../features/library/model/queryKeys";
import { isFullPaper } from "../features/library/model/types";
import type {
  FullPaper,
  LibraryFilter,
  LibraryPaperFilters,
} from "../features/library/model/types";
import { useTheme } from "../shared/theme/useTheme";

const DEFAULT_PAGE_SIZE = 10;
const SEARCH_DEBOUNCE_MS = 2000;
const DEFAULT_BULK_DRAFT: BulkIndexDraft = {
  limit: 50,
  batch_size: 50,
  force_parse: false,
  force_chunk: false,
  force_reindex: false,
  include_failed_chunks: false,
};

export function LibraryPage() {
  const queryClient = useQueryClient();
  const { theme, toggleTheme } = useTheme();
  const [filter, setFilter] = useState<LibraryFilter>("all");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [parserStatus, setParserStatus] = useState("");
  const [chunkingStatus, setChunkingStatus] = useState("");
  const [indexingStatus, setIndexingStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [selectedPaper, setSelectedPaper] = useState<FullPaper | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkDraft, setBulkDraft] =
    useState<BulkIndexDraft>(DEFAULT_BULK_DRAFT);
  const [notice, setNotice] = useState<string | null>(null);

  const paperFilters = useMemo<LibraryPaperFilters>(
    () => ({
      filter,
      query: debouncedQuery,
      parserStatus,
      chunkingStatus,
      indexingStatus,
    }),
    [chunkingStatus, debouncedQuery, filter, indexingStatus, parserStatus],
  );

  const summaryQuery = useQuery({
    queryKey: libraryKeys.summary(),
    queryFn: getLibrarySummary,
  });

  const papersQuery = useQuery({
    queryKey: libraryKeys.papers(paperFilters, page, pageSize),
    queryFn: () =>
      listLibraryPapers({
        filters: paperFilters,
        page,
        pageSize,
      }),
    refetchInterval: (query) =>
      query.state.data?.papers.some(hasActivePipeline) ? 5000 : false,
  });

  const previewQuery = useQuery({
    queryKey: libraryKeys.preview(bulkDraft),
    queryFn: () => previewPendingLibraryPapers(bulkDraft),
    enabled: bulkOpen,
  });

  const detailQuery = useQuery({
    queryKey: selectedPaper
      ? libraryKeys.paper(selectedPaper.paper_id)
      : [...libraryKeys.all, "paper", "none"],
    queryFn: () => getLibraryPaper(selectedPaper!.paper_id),
    enabled: Boolean(selectedPaper),
  });

  const detailPaper = useMemo(() => {
    const paper = detailQuery.data?.paper;
    return paper && isFullPaper(paper) ? paper : selectedPaper;
  }, [detailQuery.data?.paper, selectedPaper]);

  const invalidateLibrary = async () => {
    await queryClient.invalidateQueries({ queryKey: libraryKeys.all });
  };

  const indexMutation = useMutation({
    mutationFn: indexLibraryPaper,
    onSuccess: async (result) => {
      setNotice(
        result.status === "queued"
          ? `Queued indexing for ${result.arxiv_id}${result.task_id ? ` · task ${result.task_id}` : ""}.`
          : `${result.arxiv_id} is already indexed.`,
      );
      await invalidateLibrary();
    },
    onError: (error) => setNotice(errorMessage(error)),
  });

  const bulkIndexMutation = useMutation({
    mutationFn: indexPendingLibraryPapers,
    onSuccess: async (result) => {
      setNotice(
        `Index pending requested ${result.requested} papers: ${result.queued} queued, ${result.skipped} skipped.`,
      );
      await invalidateLibrary();
    },
    onError: (error) => setNotice(errorMessage(error)),
  });

  const deleteIndexMutation = useMutation({
    mutationFn: deleteLibraryPaperIndex,
    onSuccess: async (result) => {
      setNotice(
        `Deleted ${result.deleted_postgres_chunks} chunks and ${result.deleted_elasticsearch_documents} search documents for ${result.arxiv_id}.`,
      );
      await invalidateLibrary();
    },
    onError: (error) => setNotice(errorMessage(error)),
  });

  const deleteMetadataMutation = useMutation({
    mutationFn: deleteLibraryPaperMetadata,
    onSuccess: async (result) => {
      setNotice(`Deleted ${result.arxiv_id} from the library.`);
      setSelectedPaper(null);
      setDrawerOpen(false);
      setPage((current) =>
        papers.length <= 1 ? Math.max(1, current - 1) : current,
      );
      await invalidateLibrary();
    },
    onError: (error) => setNotice(errorMessage(error)),
  });

  const papers = papersQuery.data?.papers ?? [];
  const pages = papersQuery.data?.pages ?? 0;
  const total = papersQuery.data?.total ?? 0;
  const actionPending =
    indexMutation.isPending ||
    deleteIndexMutation.isPending ||
    deleteMetadataMutation.isPending;

  useEffect(() => {
    const searchTimer = window.setTimeout(() => {
      setDebouncedQuery(query);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(searchTimer);
  }, [query]);

  function selectFilter(nextFilter: LibraryFilter) {
    setFilter(nextFilter);
    if (nextFilter !== "all") {
      setIndexingStatus("");
    }
    setPage(1);
    setNotice(null);
  }

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
  }

  function updateParserStatus(status: string) {
    setParserStatus(status);
    setPage(1);
  }

  function updateChunkingStatus(status: string) {
    setChunkingStatus(status);
    setPage(1);
  }

  function updateIndexingStatus(status: string) {
    setIndexingStatus(status);
    setFilter("all");
    setPage(1);
  }

  function updatePageSize(nextPageSize: number) {
    setPageSize(nextPageSize);
    setPage(1);
  }

  function selectPaper(paper: FullPaper) {
    setSelectedPaper(paper);
    setDrawerOpen(true);
    setNotice(null);
  }

  function submitBulkIndex(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    bulkIndexMutation.mutate(bulkDraft);
  }

  function indexSelectedPaper(payload = {}) {
    if (!selectedPaper) return;
    setNotice(null);
    indexMutation.mutate({
      paperId: selectedPaper.paper_id,
      payload: { batch_size: 50, ...payload },
    });
  }

  function deleteSelectedIndex() {
    if (!selectedPaper) return;
    const confirmed = window.confirm(
      "Delete this paper's index? The paper record and stored artifacts will remain, but chat retrieval cannot use it until it is indexed again.",
    );
    if (!confirmed) return;
    setNotice(null);
    deleteIndexMutation.mutate(selectedPaper.paper_id);
  }

  function deleteSelectedMetadata() {
    if (!selectedPaper) return;
    const confirmed = window.confirm(
      "Delete this paper and its stored artifacts? Delete the paper index first if chunks still exist.",
    );
    if (!confirmed) return;
    setNotice(null);
    deleteMetadataMutation.mutate(selectedPaper.paper_id);
  }

  return (
    <main className={`library-shell ${drawerOpen ? "drawer-open" : ""}`}>
      {drawerOpen ? (
        <button
          className="drawer-scrim"
          type="button"
          aria-label="Close paper details"
          onClick={() => setDrawerOpen(false)}
        />
      ) : null}

      <section className="library-main">
        <header className="library-header">
          <Link className="home-brand" to="/home">
            <span className="brand-mark">arXiv</span>
            <span>Co-work</span>
          </Link>
          <nav className="home-nav" aria-label="Primary navigation">
            <Link to="/chat">
              <MessageSquareText size={15} />
              Chat
            </Link>
            <Link to="/library" aria-current="page">
              <BookOpen size={15} />
              Library
            </Link>
            <Link to="/search">
              <Search size={15} />
              Search
            </Link>
            <button
              className="icon-button"
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </nav>
        </header>

        <div className="library-content">
          <div className="library-title-row">
            <div>
              <p className="eyebrow">Corpus management</p>
              <h1>Library</h1>
              <p>
                Manage paper readiness for retrieval, indexing, and cleanup.
              </p>
            </div>
            <Link className="library-primary-link" to="/search">
              <Search size={16} />
              Search papers
            </Link>
          </div>

          <LibraryToolbar
            summary={summaryQuery.data}
            filter={filter}
            query={query}
            parserStatus={parserStatus}
            chunkingStatus={chunkingStatus}
            indexingStatus={indexingStatus}
            page={page}
            pages={pages}
            pageSize={pageSize}
            total={total}
            refreshing={papersQuery.isFetching}
            bulkOpen={bulkOpen}
            bulkDraft={bulkDraft}
            preview={previewQuery.data}
            previewLoading={previewQuery.isFetching}
            indexingPending={bulkIndexMutation.isPending}
            bulkDisabled={papersQuery.isLoading}
            onFilterChange={selectFilter}
            onQueryChange={updateQuery}
            onParserStatusChange={updateParserStatus}
            onChunkingStatusChange={updateChunkingStatus}
            onIndexingStatusChange={updateIndexingStatus}
            onRefresh={() => {
              void papersQuery.refetch();
              void summaryQuery.refetch();
              if (bulkOpen) void previewQuery.refetch();
            }}
            onPageSizeChange={updatePageSize}
            onPreviousPage={() => setPage((current) => Math.max(1, current - 1))}
            onNextPage={() =>
              setPage((current) =>
                pages === 0 ? current : Math.min(pages, current + 1),
              )
            }
            onBulkOpenChange={setBulkOpen}
            onBulkDraftChange={setBulkDraft}
            onBulkSubmit={submitBulkIndex}
          />

          {notice ? <div className="library-notice">{notice}</div> : null}

          <PaperTable
            papers={papers}
            loading={papersQuery.isLoading}
            error={papersQuery.isError}
            selectedPaperId={selectedPaper?.paper_id ?? null}
            onSelectPaper={selectPaper}
          />
        </div>
      </section>

      <PaperDetailDrawer
        paper={drawerOpen ? detailPaper : null}
        loading={detailQuery.isFetching}
        actionPending={actionPending}
        onClose={() => setDrawerOpen(false)}
        onIndex={() => indexSelectedPaper()}
        onReindex={() => indexSelectedPaper({ force_reindex: true })}
        onReprocess={() =>
          indexSelectedPaper({
            force_parse: true,
            force_chunk: true,
            force_reindex: true,
          })
        }
        onDeleteIndex={deleteSelectedIndex}
        onDeleteMetadata={deleteSelectedMetadata}
      />
    </main>
  );
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Library operation failed.";
}

function hasActivePipeline(paper: FullPaper) {
  return (
    paper.status.ingestion_status === "pdf_downloading" ||
    paper.status.parser_status === "parsing" ||
    paper.status.chunking_status === "chunking" ||
    paper.status.indexing_status === "indexing"
  );
}
