import { AlertCircle, FileText } from "lucide-react";
import { StatusChip } from "./StatusChip";
import type { FullPaper } from "../model/types";

export function PaperTable({
  papers,
  loading,
  error,
  selectedPaperId,
  onSelectPaper,
}: {
  papers: FullPaper[];
  loading: boolean;
  error: boolean;
  selectedPaperId: string | null;
  onSelectPaper: (paper: FullPaper) => void;
}) {
  if (loading) {
    return <div className="library-state">Loading papers...</div>;
  }

  if (error) {
    return (
      <div className="library-state error">
        <AlertCircle size={22} />
        Could not load the paper library.
      </div>
    );
  }

  if (papers.length === 0) {
    return (
      <div className="library-state">
        <FileText size={24} />
        No papers match this view.
      </div>
    );
  }

  return (
    <div className="paper-table-wrap">
      <table className="paper-table">
        <thead>
          <tr>
            <th>Paper</th>
            <th>Pipeline</th>
            <th>Updated</th>
            <th>Artifacts</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => (
            <tr
              className={paper.paper_id === selectedPaperId ? "selected" : ""}
              key={paper.paper_id}
              onClick={() => onSelectPaper(paper)}
            >
              <td>
                <div className="paper-title-cell">
                  <strong>{paper.metadata.title}</strong>
                  <span>
                    {paper.arxiv_id} ·{" "}
                    {paper.metadata.authors.slice(0, 3).join(", ")}
                  </span>
                  <div className="paper-category-row">
                    {paper.metadata.categories.slice(0, 4).map((category) => (
                      <span key={category}>{category}</span>
                    ))}
                  </div>
                </div>
              </td>
              <td>
                <div className="pipeline-chip-grid">
                  <StatusChip label="PDF" value={paper.status.ingestion_status} />
                  <StatusChip label="Parse" value={paper.status.parser_status} />
                  <StatusChip label="Chunk" value={paper.status.chunking_status} />
                  <StatusChip label="Index" value={paper.status.indexing_status} />
                </div>
              </td>
              <td>
                <span className="paper-date">
                  {formatDate(paper.timestamps.updated_at)}
                </span>
              </td>
              <td>
                <div className="artifact-summary">
                  <span className={paper.artifacts.pdf_object_key ? "on" : ""}>
                    PDF
                  </span>
                  <span
                    className={paper.artifacts.parsed_json_object_key ? "on" : ""}
                  >
                    Parsed
                  </span>
                  {hasErrors(paper) ? <span className="danger">Errors</span> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function hasErrors(paper: FullPaper) {
  return Boolean(
    paper.errors.pdf_download_error ||
      paper.errors.parser_error ||
      paper.errors.chunking_error ||
      paper.errors.indexing_error ||
      paper.errors.chunk_errors.length,
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
