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
  "document_id",
  "block_id",
]);

export function isDataRulesManagedColumn(value: string) {
  return managedColumns.has(value.trim().toLowerCase());
}
