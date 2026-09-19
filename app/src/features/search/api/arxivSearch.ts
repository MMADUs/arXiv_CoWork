import { api } from "../../../shared/api/client";
import type {
  ArxivPaperSearchResult,
  ArxivQueryPlanRequest,
  ArxivQueryPlanResponse,
  ArxivSearchForm,
  ArxivSearchRequest,
  ArxivSearchResponse,
  SelectedPapersIngestionResponse,
} from "../model/types";

type SmartSearchPlanRequest = ArxivQueryPlanRequest & {
  onStatus?: (text: string) => void;
  signal?: AbortSignal;
};

type SmartSearchStreamEvent =
  | {
      event: "smart_search.status";
      data: { text: string };
    }
  | {
      event: "smart_search.completed";
      data: ArxivQueryPlanResponse;
    }
  | {
      event: "smart_search.error";
      data: { message: string };
    };

export async function planArxivQuery({
  prompt,
  onStatus,
  signal,
}: SmartSearchPlanRequest) {
  const response = await fetch("/api/papers/arxiv-query-plan/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ prompt }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  if (!response.body) {
    throw new Error("The browser did not expose a response stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let plan: ArxivQueryPlanResponse | null = null;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const event = parseSmartSearchSseBlock(part);
        if (!event) continue;

        if (event.event === "smart_search.status") {
          onStatus?.(event.data.text);
        }

        if (event.event === "smart_search.completed") {
          plan = event.data;
        }

        if (event.event === "smart_search.error") {
          throw new Error(event.data.message);
        }
      }
    }

    buffer += decoder.decode();
    const finalEvent = parseSmartSearchSseBlock(buffer);
    if (finalEvent?.event === "smart_search.status") {
      onStatus?.(finalEvent.data.text);
    }
    if (finalEvent?.event === "smart_search.completed") {
      plan = finalEvent.data;
    }
    if (finalEvent?.event === "smart_search.error") {
      throw new Error(finalEvent.data.message);
    }
  } finally {
    reader.releaseLock();
  }

  if (!plan) {
    throw new Error("Smart search finished without a query plan.");
  }

  return plan;
}

export async function searchArxiv(form: ArxivSearchForm) {
  const response = await api.post<ArxivSearchResponse>(
    "/papers/arxiv-search",
    formToSearchRequest(form),
  );
  return response.data;
}

export async function ingestSelectedPapers(papers: ArxivPaperSearchResult[]) {
  const response = await api.post<SelectedPapersIngestionResponse>(
    "/papers/ingest-selected",
    {
      papers: papers.map(
        ({
          arxiv_id,
          version,
          title,
          authors,
          abstract,
          categories,
          published_date,
          pdf_url,
          doi,
        }) => ({
          arxiv_id,
          version,
          title,
          authors,
          abstract,
          categories,
          published_date,
          pdf_url,
          doi,
        }),
      ),
    },
  );
  return response.data;
}

export function formToSearchRequest(form: ArxivSearchForm): ArxivSearchRequest {
  return {
    keywords: splitTerms(form.keywords),
    title: splitTerms(form.title),
    abstract: splitTerms(form.abstract),
    authors: splitTerms(form.authors),
    categories: splitTerms(form.categories),
    exclude_categories: splitTerms(form.excludeCategories),
    ids: splitTerms(form.ids),
    submitted_from: dateToIso(form.submittedFrom),
    submitted_to: dateToIso(form.submittedTo),
    max_results: form.maxResults,
    start: 0,
    sort_by: form.sortBy,
    sort_order: form.sortOrder,
  };
}

export function planToForm(plan: ArxivQueryPlanResponse): ArxivSearchForm {
  return {
    keywords: joinTerms(plan.keywords),
    title: joinTerms(plan.title),
    abstract: joinTerms(plan.abstract),
    authors: joinTerms(plan.authors),
    categories: joinTerms(plan.categories),
    excludeCategories: joinTerms(plan.exclude_categories),
    ids: "",
    submittedFrom: isoToDateInput(plan.submitted_from),
    submittedTo: isoToDateInput(plan.submitted_to),
    maxResults: plan.max_results,
    sortBy: plan.sort_by,
    sortOrder: plan.sort_order,
  };
}

function splitTerms(value: string) {
  const terms = value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);

  return terms.length ? terms : undefined;
}

function joinTerms(value: string[] | null) {
  return value?.join(", ") ?? "";
}

function dateToIso(value: string) {
  if (!value) return undefined;
  return new Date(`${value}T00:00:00.000Z`).toISOString();
}

function isoToDateInput(value: string | null) {
  if (!value) return "";
  return value.slice(0, 10);
}

function parseSmartSearchSseBlock(block: string): SmartSearchStreamEvent | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) return null;

  const data = JSON.parse(dataLines.join("\n")) as unknown;

  switch (event) {
    case "smart_search.status":
    case "smart_search.completed":
    case "smart_search.error":
      return { event, data } as SmartSearchStreamEvent;
    default:
      return null;
  }
}
