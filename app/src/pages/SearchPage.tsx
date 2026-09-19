import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  MessageSquareText,
  Moon,
  Search,
  Sparkles,
  Sun,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ingestSelectedPapers,
  planArxivQuery,
  planToForm,
  searchArxiv,
} from "../features/search/api/arxivSearch";
import {
  DEFAULT_SEARCH_FORM,
  type ArxivPaperSearchResult,
  type ArxivSearchForm,
} from "../features/search/model/types";
import { useTheme } from "../shared/theme/useTheme";

type SearchMode = "describe" | "advanced";
type ResultFilter = "all" | "selected" | "new" | "existing";

const SEARCH_LOADING_TEXTS = [
  "Searching arXiv...",
  "Reading candidate metadata...",
  "Checking your library...",
  "Grouping useful matches...",
  "Preparing paper results...",
];
const RESULT_PAGE_SIZES = [10, 20, 50];

export function SearchPage() {
  const { theme, toggleTheme } = useTheme();
  const [mode, setMode] = useState<SearchMode>("describe");
  const [prompt, setPrompt] = useState("");
  const [requireReview, setRequireReview] = useState(true);
  const [form, setForm] = useState<ArxivSearchForm>(DEFAULT_SEARCH_FORM);
  const [results, setResults] = useState<ArxivPaperSearchResult[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [planExplanation, setPlanExplanation] = useState<string | null>(null);
  const [smartSearchStatus, setSmartSearchStatus] = useState(
    "Preparing smart search...",
  );
  const [resultQuery, setResultQuery] = useState("");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");
  const [resultPage, setResultPage] = useState(1);
  const [resultPageSize, setResultPageSize] = useState(10);

  const selectedPapers = useMemo(
    () => results.filter((paper) => selectedIds.has(paper.arxiv_id)),
    [results, selectedIds],
  );
  const filteredResults = useMemo(
    () =>
      results.filter(
        (paper) =>
          matchesResultFilter(paper, resultFilter, selectedIds) &&
          matchesResultQuery(paper, resultQuery),
      ),
    [resultFilter, resultQuery, results, selectedIds],
  );
  const resultPages = Math.max(1, Math.ceil(filteredResults.length / resultPageSize));
  const currentResultPage = Math.min(resultPage, resultPages);
  const pagedResults = useMemo(() => {
    const start = (currentResultPage - 1) * resultPageSize;
    return filteredResults.slice(start, start + resultPageSize);
  }, [currentResultPage, filteredResults, resultPageSize]);

  const planMutation = useMutation({
    mutationFn: planArxivQuery,
    onSuccess: (plan) => {
      const plannedForm = planToForm(plan);
      setForm(plannedForm);
      setPlanExplanation(plan.explanation);
      if (requireReview) {
        setMode("advanced");
        setNotice("Search fields are ready to review.");
      } else {
        setNotice("Search plan built. Searching arXiv now.");
        searchMutation.mutate(plannedForm);
      }
    },
    onError: (error) => setNotice(errorMessage(error)),
  });

  const searchMutation = useMutation({
    mutationFn: searchArxiv,
    onSuccess: (response) => {
      setResults(response.papers);
      setSelectedIds(new Set());
      setResultQuery("");
      setResultFilter("all");
      setResultPage(1);
      setNotice(`${response.count} arXiv results found.`);
    },
    onError: (error) => setNotice(errorMessage(error)),
  });

  const ingestMutation = useMutation({
    mutationFn: ingestSelectedPapers,
    onSuccess: (response) => {
      setNotice(
        `Added ${response.created} new papers, updated ${response.updated}, and queued ${response.pdf_downloads_queued} PDF downloads.`,
      );
      setSelectedIds(new Set());
      setResults((current) =>
        current.map((paper) =>
          response.papers.some((item) => item.arxiv_id === paper.arxiv_id)
            ? { ...paper, already_exists: true }
            : paper,
        ),
      );
    },
    onError: (error) => setNotice(errorMessage(error)),
  });
  const searchLoadingText = useRotatingText(
    searchMutation.isPending,
    SEARCH_LOADING_TEXTS,
  );

  function submitPlan(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    setPlanExplanation(null);
    setSmartSearchStatus("Preparing smart search...");
    planMutation.mutate({
      prompt,
      onStatus: setSmartSearchStatus,
    });
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    searchMutation.mutate(form);
  }

  function addSelected() {
    if (selectedPapers.length === 0) return;
    setNotice(null);
    ingestMutation.mutate(selectedPapers);
  }

  function togglePaper(arxivId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(arxivId)) {
        next.delete(arxivId);
      } else {
        next.add(arxivId);
      }
      return next;
    });
  }

  function updateResultQuery(value: string) {
    setResultQuery(value);
    setResultPage(1);
  }

  function updateResultFilter(value: ResultFilter) {
    setResultFilter(value);
    setResultPage(1);
  }

  function updateResultPageSize(value: number) {
    setResultPageSize(value);
    setResultPage(1);
  }

  function selectPageResults() {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const paper of pagedResults) {
        next.add(paper.arxiv_id);
      }
      return next;
    });
  }

  function selectFilteredResults() {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const paper of filteredResults) {
        next.add(paper.arxiv_id);
      }
      return next;
    });
  }

  return (
    <main className="search-page">
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
          <Link to="/library">
            <BookOpen size={15} />
            Library
          </Link>
          <Link to="/search" aria-current="page">
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

      <div className="search-content">
        <Link className="search-back-link" to="/library">
          <ArrowLeft size={16} />
          Back to library
        </Link>

        <section className="search-hero">
          <div>
            <p className="eyebrow">Paper discovery</p>
            <h1>Search arXiv</h1>
            <p>
              Find candidate papers, review them carefully, and add selected
              metadata to your library.
            </p>
          </div>
        </section>

        <section className="search-planner">
          <div className="segmented-control search-mode-tabs">
            <button
              className={mode === "describe" ? "active" : ""}
              type="button"
              onClick={() => setMode("describe")}
            >
              Describe need
            </button>
            <button
              className={mode === "advanced" ? "active" : ""}
              type="button"
              onClick={() => setMode("advanced")}
            >
              Advanced fields
            </button>
          </div>

          {mode === "describe" ? (
            <form className="describe-search-form" onSubmit={submitPlan}>
              <label>
                <span>What are you looking for?</span>
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder="Recent papers about agentic RAG evaluation and citation faithfulness"
                />
              </label>
              <label className="review-toggle-row">
                <span className="review-toggle-copy">
                  <strong>Review generated fields</strong>
                  <span>
                    {requireReview
                      ? "Check the query before searching arXiv."
                      : "Search immediately after the query is built."}
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={requireReview}
                  onChange={(event) => setRequireReview(event.target.checked)}
                />
                <span className="review-switch" aria-hidden="true" />
              </label>
              {planMutation.isPending || searchMutation.isPending ? (
                <div className="search-loading-panel" aria-live="polite">
                  <Sparkles size={17} className="spin-icon" />
                  <span>
                    {planMutation.isPending ? smartSearchStatus : searchLoadingText}
                  </span>
                </div>
              ) : null}
              <button
                className="library-primary-button"
                type="submit"
                disabled={
                  planMutation.isPending || searchMutation.isPending || !prompt.trim()
                }
              >
                <Sparkles size={16} />
                {planMutation.isPending || searchMutation.isPending
                  ? planMutation.isPending
                    ? smartSearchStatus
                    : searchLoadingText
                  : requireReview
                    ? "Build arXiv search"
                    : "Search without review"}
              </button>
            </form>
          ) : (
            <SearchFields
              form={form}
              searching={searchMutation.isPending}
              loadingText={searchLoadingText}
              planExplanation={planExplanation}
              onFormChange={setForm}
              onSubmit={submitSearch}
            />
          )}
        </section>

        {notice ? <div className="library-notice">{notice}</div> : null}

        <section className="search-results-section">
          <div className="search-results-heading">
            <div>
              <p className="eyebrow">Results</p>
              <h2>
                {results.length
                  ? `${filteredResults.length} of ${results.length} candidates`
                  : "No search yet"}
              </h2>
            </div>
          </div>

          {results.length === 0 ? (
            <div className="library-state">
              <Search size={24} />
              Search arXiv to preview candidate papers.
            </div>
          ) : (
            <>
              <div className="search-result-toolbar">
                <label className="result-local-search">
                  <Search size={16} />
                  <input
                    value={resultQuery}
                    onChange={(event) => updateResultQuery(event.target.value)}
                    placeholder="Filter returned results"
                  />
                </label>
                <div className="segmented-control result-filter-tabs">
                  <button
                    className={resultFilter === "all" ? "active" : ""}
                    type="button"
                    onClick={() => updateResultFilter("all")}
                  >
                    All
                  </button>
                  <button
                    className={resultFilter === "selected" ? "active" : ""}
                    type="button"
                    onClick={() => updateResultFilter("selected")}
                  >
                    Selected
                  </button>
                  <button
                    className={resultFilter === "new" ? "active" : ""}
                    type="button"
                    onClick={() => updateResultFilter("new")}
                  >
                    New
                  </button>
                  <button
                    className={resultFilter === "existing" ? "active" : ""}
                    type="button"
                    onClick={() => updateResultFilter("existing")}
                  >
                    In library
                  </button>
                </div>
                <label className="result-page-size">
                  <span>Rows</span>
                  <select
                    value={resultPageSize}
                    onChange={(event) =>
                      updateResultPageSize(Number(event.target.value))
                    }
                  >
                    {RESULT_PAGE_SIZES.map((size) => (
                      <option value={size} key={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="search-result-actions">
                <span>
                  Showing {pageWindowLabel(filteredResults.length, currentResultPage, resultPageSize)}
                </span>
                <div>
                  <button
                    className="library-secondary-button"
                    type="button"
                    onClick={selectPageResults}
                    disabled={pagedResults.length === 0}
                  >
                    Select page
                  </button>
                  <button
                    className="library-secondary-button"
                    type="button"
                    onClick={selectFilteredResults}
                    disabled={filteredResults.length === 0}
                  >
                    Select filtered
                  </button>
                  <button
                    className="icon-button compact"
                    type="button"
                    onClick={() => setResultPage((page) => Math.max(1, page - 1))}
                    disabled={currentResultPage <= 1}
                    aria-label="Previous result page"
                    title="Previous page"
                  >
                    <ChevronLeft size={17} />
                  </button>
                  <span className="result-page-label">
                    {currentResultPage} / {resultPages}
                  </span>
                  <button
                    className="icon-button compact"
                    type="button"
                    onClick={() =>
                      setResultPage((page) => Math.min(resultPages, page + 1))
                    }
                    disabled={currentResultPage >= resultPages}
                    aria-label="Next result page"
                    title="Next page"
                  >
                    <ChevronRight size={17} />
                  </button>
                </div>
              </div>

              {filteredResults.length === 0 ? (
                <div className="library-state">
                  <Search size={24} />
                  No returned papers match these local filters.
                </div>
              ) : (
                <div className="search-result-list">
                  {pagedResults.map((paper) => (
                    <article className="search-result-row" key={paper.arxiv_id}>
                      <label className="search-result-check">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(paper.arxiv_id)}
                          onChange={() => togglePaper(paper.arxiv_id)}
                        />
                        <span />
                      </label>
                      <div className="search-result-body">
                        <div className="search-result-topline">
                          <span>{paper.arxiv_id}</span>
                          {paper.already_exists ? (
                            <span className="library-result-badge">In library</span>
                          ) : null}
                          {paper.categories.slice(0, 4).map((category) => (
                            <span key={category}>{category}</span>
                          ))}
                        </div>
                        <h3>{paper.title}</h3>
                        <p className="search-authors">
                          {paper.authors.slice(0, 5).join(", ")}
                        </p>
                        <p className="search-abstract">{paper.abstract}</p>
                        <div className="search-result-footer">
                          <span>{formatDate(paper.published_date)}</span>
                          {paper.pdf_url ? (
                            <a href={paper.pdf_url} target="_blank" rel="noreferrer">
                              Open PDF
                              <ExternalLink size={14} />
                            </a>
                          ) : null}
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {selectedPapers.length ? (
        <div className="search-selection-bar">
          <span>{selectedPapers.length} selected</span>
          <button
            className="library-primary-button"
            type="button"
            onClick={addSelected}
            disabled={ingestMutation.isPending}
          >
            <Check size={16} />
            {ingestMutation.isPending ? "Adding..." : "Add selected to library"}
          </button>
        </div>
      ) : null}
    </main>
  );
}

function SearchFields({
  form,
  searching,
  loadingText,
  planExplanation,
  onFormChange,
  onSubmit,
}: {
  form: ArxivSearchForm;
  searching: boolean;
  loadingText: string;
  planExplanation: string | null;
  onFormChange: (form: ArxivSearchForm) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="advanced-search-form" onSubmit={onSubmit}>
      {planExplanation ? (
        <p className="query-plan-note">{planExplanation}</p>
      ) : null}

      <SearchTextField
        label="Keywords"
        value={form.keywords}
        multiline
        wide
        onChange={(value) => onFormChange({ ...form, keywords: value })}
      />
      <SearchTextField
        label="Title"
        value={form.title}
        multiline
        wide
        onChange={(value) => onFormChange({ ...form, title: value })}
      />
      <SearchTextField
        label="Abstract"
        value={form.abstract}
        multiline
        wide
        onChange={(value) => onFormChange({ ...form, abstract: value })}
      />
      <SearchTextField
        label="Authors"
        value={form.authors}
        onChange={(value) => onFormChange({ ...form, authors: value })}
      />
      <SearchTextField
        label="Categories"
        value={form.categories}
        onChange={(value) => onFormChange({ ...form, categories: value })}
      />
      <SearchTextField
        label="Exclude categories"
        value={form.excludeCategories}
        onChange={(value) => onFormChange({ ...form, excludeCategories: value })}
      />
      <SearchTextField
        label="arXiv IDs"
        value={form.ids}
        onChange={(value) => onFormChange({ ...form, ids: value })}
      />

      <label className="search-field">
        <span>From</span>
        <input
          type="date"
          value={form.submittedFrom}
          onChange={(event) =>
            onFormChange({ ...form, submittedFrom: event.target.value })
          }
        />
      </label>
      <label className="search-field">
        <span>To</span>
        <input
          type="date"
          value={form.submittedTo}
          onChange={(event) =>
            onFormChange({ ...form, submittedTo: event.target.value })
          }
        />
      </label>
      <label className="search-field">
        <span>Max results</span>
        <input
          type="number"
          min={1}
          max={100}
          value={form.maxResults}
          onChange={(event) =>
            onFormChange({ ...form, maxResults: event.target.valueAsNumber || 1 })
          }
        />
      </label>
      <label className="search-field">
        <span>Sort by</span>
        <select
          value={form.sortBy}
          onChange={(event) =>
            onFormChange({
              ...form,
              sortBy: event.target.value as ArxivSearchForm["sortBy"],
            })
          }
        >
          <option value="submittedDate">Submitted date</option>
          <option value="lastUpdatedDate">Last updated</option>
          <option value="relevance">Relevance</option>
        </select>
      </label>
      <label className="search-field">
        <span>Sort order</span>
        <select
          value={form.sortOrder}
          onChange={(event) =>
            onFormChange({
              ...form,
              sortOrder: event.target.value as ArxivSearchForm["sortOrder"],
            })
          }
        >
          <option value="descending">Descending</option>
          <option value="ascending">Ascending</option>
        </select>
      </label>

      {searching ? (
        <div className="search-loading-panel advanced" aria-live="polite">
          <Search size={17} className="spin-icon" />
          <span>{loadingText}</span>
        </div>
      ) : null}
      <button className="library-primary-button" type="submit" disabled={searching}>
        <Search size={16} />
        {searching ? loadingText : "Search arXiv"}
      </button>
    </form>
  );
}

function SearchTextField({
  label,
  value,
  multiline = false,
  wide = false,
  onChange,
}: {
  label: string;
  value: string;
  multiline?: boolean;
  wide?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className={`search-field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Comma or line separated"
        />
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Comma-separated"
        />
      )}
    </label>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function matchesResultFilter(
  paper: ArxivPaperSearchResult,
  filter: ResultFilter,
  selectedIds: Set<string>,
) {
  switch (filter) {
    case "selected":
      return selectedIds.has(paper.arxiv_id);
    case "new":
      return !paper.already_exists;
    case "existing":
      return paper.already_exists;
    default:
      return true;
  }
}

function matchesResultQuery(paper: ArxivPaperSearchResult, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;

  const searchable = [
    paper.arxiv_id,
    paper.title,
    paper.abstract,
    paper.authors.join(" "),
    paper.categories.join(" "),
  ]
    .join(" ")
    .toLowerCase();

  return searchable.includes(normalizedQuery);
}

function pageWindowLabel(total: number, page: number, pageSize: number) {
  if (total === 0) return "0 results";

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return `${start}-${end} of ${total}`;
}

function useRotatingText(active: boolean, texts: string[], intervalMs = 1400) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setIndex((current) => (current + 1) % texts.length);
    }, intervalMs);

    return () => window.clearInterval(intervalId);
  }, [active, intervalMs, texts.length]);

  return texts[index] ?? texts[0] ?? "Working...";
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Search operation failed.";
}
