const SAFE_TABLE = /^(new_table:)?[a-zA-Z_][a-zA-Z0-9_]{1,62}$/;

export function summaryText(value: unknown, fallback: unknown) {
  return textValue(value) || textValue(fallback);
}

export function summaryItems(value: unknown, limit = 6) {
  if (!Array.isArray(value)) return [];
  return value.map(formatSummaryItem).filter(Boolean).slice(0, limit);
}

export function destinationItems(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.map(formatDestination).filter(Boolean).slice(0, 5);
}

export function formatQualityWarning(item: unknown, t: (key: string) => string) {
  if (!item || typeof item !== "object") return "";
  const value = item as Record<string, unknown>;
  const count = Number(value.count ?? 0);
  if (value.key === "low_confidence") return `${t("lowConfidence")}: ${count}`;
  if (value.key === "image_pages") return `${t("pages")}: ${count}`;
  if (value.key === "empty_blocks" || value.key === "no_blocks") return `${t("blocks")}: ${count}`;
  return `${t("validation")}: ${textValue(value.key)}`;
}

export function formatPageLabel(label: string, t: (key: string) => string) {
  const [kind, ...rest] = label.split(" ");
  const index = rest.join(" ");
  if (kind === "page") return `${t("pages")} ${index}`.trim();
  if (kind === "sheet") return `${t("sheets")} ${index}`.trim();
  if (kind === "slide") return `${t("slides")} ${index}`.trim();
  return label;
}

function formatDestination(item: unknown) {
  if (typeof item === "string") return SAFE_TABLE.test(item.trim()) ? item.trim() : "";
  if (!item || typeof item !== "object") return "";
  const value = item as Record<string, unknown>;
  const table = textValue(value.table_name ?? value.name ?? value.value).replace(/^new_table:/, "");
  if (!SAFE_TABLE.test(table)) return "";
  const reason = textValue(value.reason ?? value.description);
  return [table, reason].filter(Boolean).join(" — ");
}

function formatSummaryItem(item: unknown) {
  if (typeof item === "string" || typeof item === "number") return String(item);
  if (!item || typeof item !== "object") return "";
  const value = item as Record<string, unknown>;
  const main = textValue(value.name ?? value.table_name ?? value.title ?? value.entity ?? value.label);
  const type = textValue(value.type ?? value.value_or_role ?? value.role ?? value.category);
  const extra = textValue(value.value ?? value.amount ?? value.date ?? value.reason ?? value.summary);
  const known = [main, type, extra].filter(Boolean).join(" — ");
  return known || objectPreview(value);
}

function objectPreview(value: Record<string, unknown>) {
  return Object.entries(value)
    .filter(([, item]) => item !== null && item !== undefined && typeof item !== "object")
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${String(item)}`)
    .join(" · ");
}

function textValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value).trim();
  }
  return "";
}
