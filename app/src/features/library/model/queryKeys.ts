import type { LibraryPaperFilters } from "./types";

export const libraryKeys = {
  all: ["library"] as const,
  summary: () => [...libraryKeys.all, "summary"] as const,
  papers: (filters: LibraryPaperFilters, page: number, pageSize: number) =>
    [...libraryKeys.all, "papers", filters, page, pageSize] as const,
  paper: (paperId: string) => [...libraryKeys.all, "paper", paperId] as const,
  preview: (payload: unknown) => [...libraryKeys.all, "preview", payload] as const,
};
