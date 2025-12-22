"""CSV import service with validation, normalization, and preview support"""
import csv
import io
import os
import uuid
import json
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.models.lead import Lead, GraduationYearSource
from src.ma_tool.models.user import User
from src.ma_tool.services.audit import log_action
from src.ma_tool.services.csv_normalizer import (
    auto_map_columns,
    map_column_name,
    normalize_email,
    normalize_grade_label,
    normalize_consent,
    normalize_name,
    normalize_text,
)
from src.ma_tool.schemas.csv_import import (
    MappingPreview,
    ColumnMapping,
    RowPreview,
    DryRunResult,
    ImportResult,
    ImportError as ImportErrorSchema,
)
from src.ma_tool.schemas.lead import CSVImportResult

IMPORT_SESSIONS: Dict[str, Dict[str, Any]] = {}

HARD_REQUIRED = ["email", "consent"]
SOFT_REQUIRED = ["name", "school_name", "interest_tags"]


def decode_csv_content(content: bytes) -> str:
    encodings = ["utf-8", "utf-8-sig", "cp932", "shift-jis", "euc-jp"]
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("Unable to decode CSV file. Supported encodings: UTF-8, CP932, Shift-JIS")


def estimate_graduation_year_from_grade(grade: int) -> int:
    today = datetime.now()
    current_year = today.year
    current_month = today.month
    
    if current_month >= 4:
        school_year_start = current_year
    else:
        school_year_start = current_year - 1
    
    years_until_graduation = 3 - grade + 1
    graduation_year = school_year_start + years_until_graduation
    
    return graduation_year


def validate_and_normalize_row(
    row: Dict[str, str],
    mapping: Dict[str, str],
    row_num: int
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    errors = []
    warnings = []
    normalized = {}
    
    mapped_row = {}
    for orig_col, value in row.items():
        if orig_col in mapping:
            mapped_row[mapping[orig_col]] = value
    
    email_raw = mapped_row.get("email", "").strip()
    if not email_raw:
        errors.append("email is required (hard required)")
    else:
        email = normalize_email(email_raw)
        try:
            validated = validate_email(email, check_deliverability=False)
            normalized["email"] = validated.email
        except EmailNotValidError as e:
            errors.append(f"invalid email format: {str(e)}")
    
    consent_raw = mapped_row.get("consent", "").strip()
    if not consent_raw:
        errors.append("consent is required (hard required)")
    else:
        consent_val, is_ambiguous = normalize_consent(consent_raw)
        if is_ambiguous:
            errors.append(f"ambiguous consent value: '{consent_raw}' (use true/false, yes/no, 同意あり/なし)")
        elif consent_val is not None:
            normalized["consent"] = consent_val
    
    graduation_year_raw = mapped_row.get("graduation_year", "").strip()
    grade_label_raw = mapped_row.get("grade_label", "").strip()
    
    if graduation_year_raw:
        try:
            year = int(graduation_year_raw)
            if year < 2000 or year > 2100:
                errors.append("graduation_year must be between 2000 and 2100")
            else:
                normalized["graduation_year"] = year
                normalized["graduation_year_source"] = GraduationYearSource.CSV
        except ValueError:
            errors.append(f"graduation_year must be a valid integer: '{graduation_year_raw}'")
    elif grade_label_raw:
        grade = normalize_grade_label(grade_label_raw)
        if grade:
            normalized["graduation_year"] = estimate_graduation_year_from_grade(grade)
            normalized["graduation_year_source"] = GraduationYearSource.ESTIMATED
        else:
            errors.append(f"could not parse grade_label: '{grade_label_raw}' (use 高1/高2/高3 or 1/2/3)")
    else:
        errors.append("graduation_year or grade_label is required (hard required)")
    
    name_raw = mapped_row.get("name", "").strip()
    if name_raw:
        normalized["name"] = normalize_name(name_raw)
    else:
        warnings.append("name is missing (soft required)")
        normalized["name"] = ""
    
    school_name_raw = mapped_row.get("school_name", "").strip()
    if school_name_raw:
        normalized["school_name"] = normalize_text(school_name_raw)
    else:
        warnings.append("school_name is missing (soft required)")
        normalized["school_name"] = None
    
    interest_tags_raw = mapped_row.get("interest_tags", "").strip()
    if interest_tags_raw:
        normalized["interest_tags"] = normalize_text(interest_tags_raw)
    else:
        warnings.append("interest_tags is missing (soft required)")
        normalized["interest_tags"] = None
    
    return normalized, errors, warnings


def create_mapping_preview(headers: List[str]) -> MappingPreview:
    auto_mapping = auto_map_columns(headers)
    
    columns = []
    unmapped = []
    mapped_targets = set()
    
    for header in headers:
        if header in auto_mapping:
            canonical = auto_mapping[header]
            _, confidence = map_column_name(header)
            columns.append(ColumnMapping(
                original=header,
                mapped_to=canonical,
                confidence=confidence
            ))
            mapped_targets.add(canonical)
        else:
            columns.append(ColumnMapping(
                original=header,
                mapped_to=None,
                confidence=0.0
            ))
            unmapped.append(header)
    
    all_required = set(HARD_REQUIRED) | {"graduation_year", "grade_label"}
    missing = []
    for req in HARD_REQUIRED:
        if req not in mapped_targets:
            missing.append(req)
    
    if "graduation_year" not in mapped_targets and "grade_label" not in mapped_targets:
        missing.append("graduation_year or grade_label")
    
    return MappingPreview(
        columns=columns,
        unmapped_columns=unmapped,
        missing_required=missing
    )


def dry_run_import(
    csv_content: str,
    custom_mapping: Optional[Dict[str, str]] = None,
    preview_limit: int = 20
) -> DryRunResult:
    session_id = str(uuid.uuid4())
    
    reader = csv.DictReader(io.StringIO(csv_content))
    headers = reader.fieldnames or []
    
    if custom_mapping:
        mapping = custom_mapping
    else:
        mapping = auto_map_columns(headers)
    
    mapping_preview = create_mapping_preview(headers)
    if custom_mapping:
        for col in mapping_preview.columns:
            if col.original in custom_mapping:
                col.mapped_to = custom_mapping[col.original]
    
    rows = list(reader)
    total_rows = len(rows)
    
    will_add = 0
    will_update = 0
    will_skip = 0
    error_count = 0
    warning_count = 0
    preview_rows = []
    all_rows_data = []
    
    from src.ma_tool.database import SessionLocal
    db = SessionLocal()
    
    try:
        for idx, row in enumerate(rows):
            row_num = idx + 2
            normalized, errors, warnings = validate_and_normalize_row(row, mapping, row_num)
            
            row_data = {
                "row_number": row_num,
                "original": row,
                "normalized": normalized,
                "errors": errors,
                "warnings": warnings
            }
            all_rows_data.append(row_data)
            
            if errors:
                error_count += 1
                will_skip += 1
            else:
                email = normalized.get("email")
                if email:
                    existing = db.execute(
                        select(Lead).where(Lead.email == email)
                    ).scalar_one_or_none()
                    if existing:
                        will_update += 1
                    else:
                        will_add += 1
                else:
                    will_skip += 1
            
            if warnings:
                warning_count += len(warnings)
            
            if idx < preview_limit:
                normalized_display = {}
                for k, v in normalized.items():
                    if isinstance(v, GraduationYearSource):
                        normalized_display[k] = v.value
                    else:
                        normalized_display[k] = v
                
                preview_rows.append(RowPreview(
                    row_number=row_num,
                    original=row,
                    normalized=normalized_display,
                    errors=errors,
                    warnings=warnings
                ))
    finally:
        db.close()
    
    IMPORT_SESSIONS[session_id] = {
        "csv_content": csv_content,
        "mapping": mapping,
        "rows_data": all_rows_data,
        "created_at": datetime.now()
    }
    
    return DryRunResult(
        total_rows=total_rows,
        will_add=will_add,
        will_update=will_update,
        will_skip=will_skip,
        error_count=error_count,
        warning_count=warning_count,
        preview_rows=preview_rows,
        mapping=mapping_preview,
        session_id=session_id
    )


def execute_import(
    db: Session,
    session_id: str,
    actor: User,
    updated_mapping: Optional[Dict[str, str]] = None
) -> ImportResult:
    if session_id not in IMPORT_SESSIONS:
        raise ValueError("Invalid or expired session ID. Please run preview again.")
    
    session_data = IMPORT_SESSIONS[session_id]
    csv_content = session_data["csv_content"]
    mapping = updated_mapping or session_data["mapping"]
    
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)
    
    added = 0
    updated = 0
    skipped = 0
    errors = []
    warnings_list = []
    
    for idx, row in enumerate(rows):
        row_num = idx + 2
        normalized, row_errors, row_warnings = validate_and_normalize_row(row, mapping, row_num)
        
        if row_warnings:
            warnings_list.append({
                "row_number": row_num,
                "warnings": row_warnings,
                "email": normalized.get("email", "")
            })
        
        if row_errors:
            errors.append(ImportErrorSchema(
                row_number=row_num,
                errors=row_errors,
                original_data=row
            ))
            skipped += 1
            continue
        
        if not normalized.get("name"):
            normalized["name"] = normalized.get("email", "").split("@")[0]
        
        try:
            existing = db.execute(
                select(Lead).where(Lead.email == normalized["email"])
            ).scalar_one_or_none()
            
            if existing:
                existing.name = normalized["name"]
                existing.school_name = normalized.get("school_name")
                existing.graduation_year = normalized["graduation_year"]
                existing.graduation_year_source = normalized.get(
                    "graduation_year_source", GraduationYearSource.CSV
                )
                existing.interest_tags = normalized.get("interest_tags")
                existing.consent = normalized["consent"]
                updated += 1
            else:
                lead = Lead(**normalized)
                db.add(lead)
                added += 1
        except Exception as e:
            errors.append(ImportErrorSchema(
                row_number=row_num,
                errors=[str(e)],
                original_data=row
            ))
            skipped += 1
    
    db.commit()
    
    error_csv_path = None
    if errors:
        error_csv_path = generate_error_csv(errors, session_id)
    
    del IMPORT_SESSIONS[session_id]
    
    log_action(
        db=db,
        actor=actor,
        action="LEAD_IMPORTED",
        target_type="lead",
        meta={
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "error_count": len(errors),
            "warning_count": len(warnings_list)
        }
    )
    
    return ImportResult(
        added=added,
        updated=updated,
        skipped=skipped,
        errors=errors,
        warnings=warnings_list,
        total_processed=added + updated + skipped,
        error_csv_available=error_csv_path is not None,
        error_csv_path=error_csv_path
    )


def generate_error_csv(errors: List[ImportErrorSchema], session_id: str) -> str:
    error_dir = "/tmp/csv_errors"
    os.makedirs(error_dir, exist_ok=True)
    
    filename = f"errors_{session_id[:8]}.csv"
    filepath = os.path.join(error_dir, filename)
    
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        if errors:
            first_error = errors[0]
            fieldnames = ["row_number", "errors"] + list(first_error.original_data.keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for error in errors:
                row = {
                    "row_number": error.row_number,
                    "errors": "; ".join(error.errors),
                    **error.original_data
                }
                writer.writerow(row)
    
    return filepath


def import_csv(
    db: Session,
    csv_content: str,
    actor: User
) -> CSVImportResult:
    reader = csv.DictReader(io.StringIO(csv_content))
    headers = reader.fieldnames or []
    mapping = auto_map_columns(headers)
    
    rows = list(reader)
    added = 0
    updated = 0
    errors = []
    
    for idx, row in enumerate(rows):
        row_num = idx + 2
        normalized, row_errors, _ = validate_and_normalize_row(row, mapping, row_num)
        
        if row_errors:
            errors.append({"row": row_num, "errors": row_errors, "data": row})
            continue
        
        if not normalized.get("name"):
            normalized["name"] = normalized.get("email", "").split("@")[0]
        
        existing = db.execute(
            select(Lead).where(Lead.email == normalized["email"])
        ).scalar_one_or_none()
        
        if existing:
            existing.name = normalized["name"]
            existing.school_name = normalized.get("school_name")
            existing.graduation_year = normalized["graduation_year"]
            existing.graduation_year_source = normalized.get(
                "graduation_year_source", GraduationYearSource.CSV
            )
            existing.interest_tags = normalized.get("interest_tags")
            existing.consent = normalized["consent"]
            updated += 1
        else:
            lead = Lead(**normalized)
            db.add(lead)
            added += 1
    
    db.commit()
    
    log_action(
        db=db,
        actor=actor,
        action="LEAD_IMPORTED",
        target_type="lead",
        meta={"added": added, "updated": updated, "error_count": len(errors)}
    )
    
    return CSVImportResult(
        added=added,
        updated=updated,
        errors=errors,
        total_processed=added + updated + len(errors)
    )
