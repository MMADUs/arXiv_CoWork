export function StatusChip({
  label,
  value,
}: {
  label?: string;
  value: string;
}) {
  return (
    <span className={`status-chip ${statusTone(value)}`}>
      {label ? <span>{label}</span> : null}
      {formatStatus(value)}
    </span>
  );
}

function formatStatus(value: string) {
  return value.replaceAll("_", " ");
}

function statusTone(value: string) {
  if (value.includes("failed")) return "danger";
  if (value.includes("ing") || value === "parsing") return "active";
  if (
    value === "indexed" ||
    value === "chunked" ||
    value === "parsed" ||
    value === "pdf_stored"
  ) {
    return "success";
  }
  if (value === "pending" || value === "metadata_fetched") return "pending";
  return "neutral";
}
