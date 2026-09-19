export type ArxivSortBy = "relevance" | "lastUpdatedDate" | "submittedDate";
export type ArxivSortOrder = "ascending" | "descending";

export type ArxivSearchForm = {
  keywords: string;
  title: string;
  abstract: string;
  authors: string;
  categories: string;
  excludeCategories: string;
  ids: string;
  submittedFrom: string;
  submittedTo: string;
  maxResults: number;
  sortBy: ArxivSortBy;
  sortOrder: ArxivSortOrder;
};

export type ArxivSearchRequest = {
  keywords?: string[];
  title?: string[];
  abstract?: string[];
  authors?: string[];
  categories?: string[];
  exclude_categories?: string[];
  ids?: string[];
  submitted_from?: string;
  submitted_to?: string;
  max_results: number;
  start: number;
  sort_by: ArxivSortBy;
  sort_order: ArxivSortOrder;
};

export type ArxivPaperSearchResult = {
  arxiv_id: string;
  version: number | null;
  title: string;
  authors: string[];
  abstract: string;
  categories: string[];
  published_date: string;
  pdf_url: string | null;
  doi: string | null;
  already_exists: boolean;
  existing_paper_id: string | null;
};

export type ArxivSearchResponse = {
  count: number;
  papers: ArxivPaperSearchResult[];
};

export type ArxivQueryPlanRequest = {
  prompt: string;
};

export type ArxivQueryPlanResponse = {
  keywords: string[] | null;
  title: string[] | null;
  abstract: string[] | null;
  authors: string[] | null;
  categories: string[] | null;
  exclude_categories: string[] | null;
  submitted_from: string | null;
  submitted_to: string | null;
  max_results: number;
  sort_by: ArxivSortBy;
  sort_order: ArxivSortOrder;
  explanation: string;
};

export type SelectedPapersIngestionResponse = {
  requested: number;
  created: number;
  updated: number;
  pdf_downloads_queued: number;
  pdf_downloads_skipped: number;
  papers: Array<{
    paper_id: string;
    arxiv_id: string | null;
    title: string | null;
    authors: string[];
    categories: string[];
    published_date: string | null;
    pdf_download_task_id: string | null;
    pdf_download_status: string | null;
  }>;
};

export const DEFAULT_SEARCH_FORM: ArxivSearchForm = {
  keywords: "",
  title: "",
  abstract: "",
  authors: "",
  categories: "",
  excludeCategories: "",
  ids: "",
  submittedFrom: "",
  submittedTo: "",
  maxResults: 20,
  sortBy: "submittedDate",
  sortOrder: "descending",
};
