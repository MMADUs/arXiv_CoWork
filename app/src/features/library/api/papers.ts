import { api } from "../../../shared/api/client";
import type {
  DeletePaperIndexResponse,
  DeletePaperMetadataResponse,
  FullPaper,
  IndexPaperPayload,
  IndexPaperResponse,
  IndexPapersResponse,
  IndexPendingPapersPayload,
  IndexPreviewResponse,
  LibraryPaperFilters,
  PaperDetailResponse,
  PaperListResponse,
  PaperSummaryResponse,
  TaskStatusResponse,
} from "../model/types";

export async function listLibraryPapers({
  filters,
  page,
  pageSize,
}: {
  filters: LibraryPaperFilters;
  page: number;
  pageSize: number;
}) {
  const response = await api.get<PaperListResponse<FullPaper>>("/papers", {
    params: {
      output: "full",
      page,
      page_size: pageSize,
      q: filters.query.trim() || undefined,
      status: filters.filter === "failed" ? "failed" : undefined,
      parser_status: filters.parserStatus || undefined,
      chunking_status: filters.chunkingStatus || undefined,
      indexing_status:
        filters.indexingStatus ||
        mappedIndexingStatusFromFilter(filters.filter) ||
        undefined,
    },
  });

  return response.data;
}

export async function getLibrarySummary() {
  const response = await api.get<PaperSummaryResponse>("/papers/summary");
  return response.data;
}

export async function getLibraryPaper(paperId: string) {
  const response = await api.get<PaperDetailResponse>(`/papers/${paperId}`, {
    params: { output: "full" },
  });

  return response.data;
}

export async function indexLibraryPaper({
  paperId,
  payload,
}: {
  paperId: string;
  payload: IndexPaperPayload;
}) {
  const response = await api.post<IndexPaperResponse>(
    `/papers/${paperId}/index`,
    normalizeIndexPayload(payload),
  );

  return response.data;
}

export async function indexPendingLibraryPapers(
  payload: IndexPendingPapersPayload,
) {
  const response = await api.post<IndexPapersResponse>(
    "/papers/index",
    normalizeIndexPayload(payload),
  );

  return response.data;
}

export async function previewPendingLibraryPapers(
  payload: IndexPendingPapersPayload,
) {
  const response = await api.get<IndexPreviewResponse>("/papers/index/preview", {
    params: normalizeIndexPayload(payload),
  });

  return response.data;
}

export async function deleteLibraryPaperIndex(paperId: string) {
  const response = await api.delete<DeletePaperIndexResponse>(
    `/papers/${paperId}/index`,
  );

  return response.data;
}

export async function deleteLibraryPaperMetadata(paperId: string) {
  const response = await api.delete<DeletePaperMetadataResponse>(
    `/papers/${paperId}`,
  );

  return response.data;
}

export async function getTaskStatus(taskId: string) {
  const response = await api.get<TaskStatusResponse>(`/tasks/${taskId}`);
  return response.data;
}

function normalizeIndexPayload<TPayload extends IndexPaperPayload>(
  payload: TPayload,
): Required<IndexPaperPayload> & Partial<TPayload> {
  return {
    force_parse: payload.force_parse ?? false,
    force_chunk: payload.force_chunk ?? false,
    force_reindex: payload.force_reindex ?? false,
    include_failed_chunks: payload.include_failed_chunks ?? false,
    batch_size: payload.batch_size ?? 50,
    ...payload,
  };
}

function mappedIndexingStatusFromFilter(filter: string) {
  switch (filter) {
    case "indexed":
      return "indexed";
    case "pending":
      return "pending";
    case "indexing":
      return "indexing";
    default:
      return null;
  }
}
