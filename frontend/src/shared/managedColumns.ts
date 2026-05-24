const managedColumns = new Set([
  "id",
  "content",
  "source_document_id",
  "source_block_id",
  "source_file",
  "page",
  "sheet",
  "confidence",
  "field_values",
  "field_sources",
  "metadata",
  "created_at",
]);

export function isDataRulesManagedColumn(value: string) {
  return managedColumns.has(value.trim().toLowerCase());
}
