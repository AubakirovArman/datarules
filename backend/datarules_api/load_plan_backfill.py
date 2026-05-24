from .field_provenance import normalize_field_sources
from .load_explain import attach_preview_explainability
from .models import LoadPlan


def ensure_field_sources(plan: LoadPlan) -> bool:
    rows = []
    changed = False
    for row in plan.preview_rows or []:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        fields = row.get("field_values") if isinstance(row.get("field_values"), dict) else {}
        if not row.get("field_sources"):
            row = {**row, "field_sources": normalize_field_sources(row, fields)}
            changed = True
        rows.append(row)
    if changed:
        plan.preview_rows = attach_preview_explainability(rows, plan.schema_json or {})
    return changed
