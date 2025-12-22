"""CSV import service with validation"""
import csv
import io
from typing import List, Tuple
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.models.lead import Lead
from src.ma_tool.models.user import User
from src.ma_tool.services.audit import log_action
from src.ma_tool.schemas.lead import CSVImportResult


def validate_row(row: dict, row_num: int) -> Tuple[bool, dict, List[str]]:
    errors = []
    cleaned = {}
    
    email = row.get("email", "").strip()
    if not email:
        errors.append("email is required")
    else:
        try:
            validated = validate_email(email, check_deliverability=False)
            cleaned["email"] = validated.email
        except EmailNotValidError as e:
            errors.append(f"invalid email format: {str(e)}")
    
    name = row.get("name", "").strip()
    if not name:
        errors.append("name is required")
    cleaned["name"] = name
    
    graduation_year = row.get("graduation_year", "").strip()
    if not graduation_year:
        errors.append("graduation_year is required")
    else:
        try:
            year = int(graduation_year)
            if year < 2000 or year > 2100:
                errors.append("graduation_year must be between 2000 and 2100")
            cleaned["graduation_year"] = year
        except ValueError:
            errors.append("graduation_year must be a valid integer")
    
    consent_str = row.get("consent", "").strip().lower()
    if consent_str in ("true", "1", "yes"):
        cleaned["consent"] = True
    elif consent_str in ("false", "0", "no"):
        cleaned["consent"] = False
    else:
        errors.append("consent is required and must be true/false")
    
    cleaned["school_name"] = row.get("school_name", "").strip() or None
    cleaned["interest_tags"] = row.get("interest_tags", "").strip() or None
    
    return len(errors) == 0, cleaned, errors


def import_csv(
    db: Session,
    csv_content: str,
    actor: User
) -> CSVImportResult:
    added = 0
    updated = 0
    errors = []
    
    reader = csv.DictReader(io.StringIO(csv_content))
    
    for row_num, row in enumerate(reader, start=2):
        is_valid, cleaned, row_errors = validate_row(row, row_num)
        
        if not is_valid:
            errors.append({"row": row_num, "errors": row_errors, "data": row})
            continue
        
        existing = db.execute(
            select(Lead).where(Lead.email == cleaned["email"])
        ).scalar_one_or_none()
        
        if existing:
            existing.name = cleaned["name"]
            existing.school_name = cleaned["school_name"]
            existing.graduation_year = cleaned["graduation_year"]
            existing.interest_tags = cleaned["interest_tags"]
            existing.consent = cleaned["consent"]
            updated += 1
        else:
            lead = Lead(**cleaned)
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
