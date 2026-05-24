from typing import Any

from sqlalchemy.orm import Session

from .db_identifiers import identifier_issues
from .document_quality import build_quality_profile, quality_load_issues
from .load_modes import is_analysis_only
from .models import DatabaseConnection, Document, DocumentBlock, DocumentReview, TableCatalog
from .row_review import REJECTED, row_is_loadable, row_review_counts
from .source_integrity import source_reference_issues
from .target_compatibility import target_compatibility_issues
from .write_policy import connection_can_write, write_denial


def validation_issues(
    db: Session,
    dataset_id: str,
    rows: list[dict[str, Any]],
    connection: DatabaseConnection | None,
    schema_name: str,
    target_mode: str,
    target_table: str,
    schema_json: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issues.extend(identifier_issues(schema_name, target_table, {}))
    reviews = {review.document_id: review for review in db.query(DocumentReview).filter(DocumentReview.dataset_id == dataset_id).all()}
    unconfirmed = _unconfirmed_preview_documents(rows, reviews)
    mismatched = [] if is_analysis_only(target_mode, target_table) else _mismatched_preview_documents(rows, reviews, target_table)
    if not rows:
        issues.append({"severity": "error", "code": "no_rows", "message": "No extracted rows available for loading."})
    elif not any(row_is_loadable(row) for row in rows):
        issues.append({
            "severity": "error",
            "code": "no_loadable_rows",
            "message": "No preview rows are approved or safe enough to load.",
        })
    connection_id = connection.id if connection else None
    if not connection_id:
        issues.append({"severity": "error", "code": "no_connection", "message": "No database connection is configured."})
    elif not connection_can_write(connection, schema_name):
        issues.append(write_denial(connection, schema_name))
    if target_mode == "existing" and connection_id and not _catalog_exists(db, connection_id, schema_name, target_table):
        issues.append({
            "severity": "error",
            "code": "unknown_table_catalog",
            "message": "Selected table is not in the table catalog yet.",
        })
    issues.extend(target_compatibility_issues(connection, schema_name, target_mode, target_table, schema_json))
    if target_mode == "existing" and not _confirmed_document_ids(db, dataset_id, target_table):
        issues.append({
            "severity": "warning",
            "code": "no_confirmed_target",
            "message": "No document is confirmed for the selected target table yet.",
        })
    if unconfirmed:
        issues.append({
            "severity": "error",
            "code": "unconfirmed_routes",
            "count": len(unconfirmed),
            "message": f"{len(unconfirmed)} document routing choices are not confirmed.",
        })
    if mismatched:
        issues.append({
            "severity": "error",
            "code": "route_target_mismatch",
            "count": len(mismatched),
            "message": f"{len(mismatched)} preview source document(s) are routed to a different table.",
        })
    issues.extend(source_reference_issues(db, dataset_id, rows))
    issues.extend(_document_quality_issues(db, rows))
    invalid = sum(1 for row in rows if row.get("validation_errors"))
    if invalid:
        issues.append({
            "severity": "error",
            "code": "row_validation_warnings",
            "count": invalid,
            "message": f"{invalid} preview rows need review before loading.",
        })
    low_conf = sum(1 for row in rows if float(row.get("confidence") or 0) < 0.75)
    if low_conf:
        issues.append({"severity": "warning", "code": "low_confidence_rows", "count": low_conf})
    review = row_review_counts(rows)
    if review.get(REJECTED):
        issues.append({"severity": "warning", "code": "rejected_rows", "count": review[REJECTED]})
    if review.get("needs_review"):
        issues.append({"severity": "warning", "code": "row_review_needed", "count": review["needs_review"]})
    return issues


def _catalog_exists(db: Session, connection_id: str, schema_name: str, target_table: str) -> bool:
    return bool(
        db.query(TableCatalog.id)
        .filter(TableCatalog.connection_id == connection_id)
        .filter(TableCatalog.schema_name == schema_name)
        .filter(TableCatalog.table_name == target_table)
        .first()
    )


def _confirmed_document_ids(db: Session, dataset_id: str, target_table: str) -> list[str]:
    return [
        row[0]
        for row in db.query(DocumentReview.document_id)
        .filter(DocumentReview.dataset_id == dataset_id)
        .filter(DocumentReview.status == "confirmed")
        .filter(DocumentReview.selected_table == target_table)
        .all()
    ]


def _unconfirmed_preview_documents(rows: list[dict[str, Any]], reviews: dict[str, DocumentReview]) -> list[str]:
    document_ids = sorted({str(row.get("source_document_id")) for row in rows if row.get("source_document_id")})
    return [document_id for document_id in document_ids if reviews.get(document_id) is None or reviews[document_id].status != "confirmed"]


def _mismatched_preview_documents(rows: list[dict[str, Any]], reviews: dict[str, DocumentReview], target_table: str) -> list[str]:
    document_ids = sorted({str(row.get("source_document_id")) for row in rows if row.get("source_document_id")})
    return [
        document_id
        for document_id in document_ids
        if reviews.get(document_id)
        and reviews[document_id].status == "confirmed"
        and reviews[document_id].selected_table != target_table
    ]


def _document_quality_issues(db: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    document_ids = sorted({str(row.get("source_document_id")) for row in rows if row.get("source_document_id")})
    issues: list[dict[str, Any]] = []
    for document_id in document_ids:
        document = db.get(Document, document_id)
        if not document:
            continue
        blocks = db.query(DocumentBlock).filter(DocumentBlock.document_id == document_id).all()
        issues.extend(quality_load_issues(document.id, document.file_name, build_quality_profile(blocks)))
    return issues
