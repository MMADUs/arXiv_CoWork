export type PaperOutputMode = "compact" | "full";

export type PaperListStatusFilter = "failed";

export type PaperMetadata = {
  version: number | null;
  title: string;
  authors: string[];
  abstract: string;
  categories: string[];
  published_date: string;
  pdf_url: string;
  doi: string | null;
};

export type PaperArtifacts = {
  pdf_object_key: string | null;
  parsed_json_object_key: string | null;
  parser_name: string | null;
};

export type PaperStatus = {
  ingestion_status: string;
  parser_status: string;
  chunking_status: string;
  indexing_status: string;
};

export type PaperChunkError = {
  stage: "embedding" | "indexing";
  message: string;
  count: number;
};

export type PaperErrors = {
  pdf_download_error: string | null;
  parser_error: string | null;
  chunking_error: string | null;
  indexing_error: string | null;
  chunk_errors: PaperChunkError[];
};

export type PaperTimestamps = {
  created_at: string;
  updated_at: string;
};

export type FullPaper = {
  paper_id: string;
  arxiv_id: string;
  metadata: PaperMetadata;
  artifacts: PaperArtifacts;
  status: PaperStatus;
  errors: PaperErrors;
  timestamps: PaperTimestamps;
};

export type CompactPaper = {
  paper_id: string;
  arxiv_id: string;
  title: string;
  authors: string[];
  categories: string[];
  published_date: string;
};

export type Paper = FullPaper | CompactPaper;

export type PaperListResponse<TPaper extends Paper = Paper> = {
  output: PaperOutputMode;
  status: PaperListStatusFilter | null;
  count: number;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  offset: number;
  papers: TPaper[];
};

export type PaperDetailResponse = {
  output: PaperOutputMode;
  paper: Paper;
};

export type IndexPaperPayload = {
  force_parse?: boolean;
  force_chunk?: boolean;
  force_reindex?: boolean;
  include_failed_chunks?: boolean;
  batch_size?: number;
};

export type IndexPendingPapersPayload = IndexPaperPayload & {
  limit?: number;
};

export type IndexPaperStatus =
  | "queued"
  | "already_parsing"
  | "already_chunking"
  | "already_indexing"
  | "already_indexed"
  | "no_pdf";

export type IndexPaperItem = {
  paper_id: string;
  arxiv_id: string;
  title: string;
  parser_status: string;
  chunking_status: string;
  indexing_status: string;
  task_id: string | null;
  status: IndexPaperStatus;
};

export type IndexPaperResponse = {
  paper_id: string;
  arxiv_id: string;
  title: string;
  task_id: string | null;
  status: "queued" | "already_indexed";
};

export type IndexPapersResponse = {
  requested: number;
  queued: number;
  skipped: number;
  papers: IndexPaperItem[];
};

export type IndexPreviewResponse = {
  requested: number;
  papers: IndexPaperItem[];
};

export type DeletePaperIndexResponse = {
  paper_id: string;
  arxiv_id: string;
  title: string;
  deleted_postgres_chunks: number;
  deleted_elasticsearch_documents: number;
  elasticsearch_index_exists: boolean;
  elasticsearch_version_conflicts: number;
  elasticsearch_failures: unknown[];
  status: "index_deleted";
};

export type DeletePaperMetadataResponse = {
  paper_id: string;
  arxiv_id: string;
  title: string;
  deleted_metadata: boolean;
  deleted_pdf: boolean;
  deleted_parsed_json: boolean;
  status: "metadata_deleted";
};

export type PaperSummaryResponse = {
  total: number;
  indexed: number;
  pending_indexing: number;
  failed: number;
  processing: number;
  missing_pdf: number;
};

export type TaskStatusResponse = {
  task_id: string;
  state: string;
  ready: boolean;
  successful: boolean;
  failed: boolean;
  result: unknown | null;
  error: string | null;
};

export type LibraryFilter = "all" | "failed" | "indexed" | "pending" | "indexing";

export type LibraryPaperFilters = {
  filter: LibraryFilter;
  query: string;
  parserStatus: string;
  chunkingStatus: string;
  indexingStatus: string;
};

export function isFullPaper(paper: Paper): paper is FullPaper {
  return "metadata" in paper;
}
