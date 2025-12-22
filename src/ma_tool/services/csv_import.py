"""CSV import service with validation"""
import csv
import io
import re
from datetime import datetime
from typing import List, Tuple, Optional
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.models.lead import Lead, GraduationYearSource
from src.ma_tool.models.user import User
from src.ma_tool.services.audit import log_action
from src.ma_tool.schemas.lead import CSVImportResult


GRADE_LABEL_MAP = {
    "高1": 1, "高2": 2, "高3": 3,
    "1": 1, "2": 2, "3": 3,
    "1年": 1, "2年": 2, "3年": 3,
    "高校1年": 1, "高校2年": 2, "高校3年": 3,
}


def estimate_graduation_year_from_grade(grade_label: str) -> Optional[int]:
    grade_label = grade_label.strip()
    grade = GRADE_LABEL_MAP.get(grade_label)
    
    if grade is None:
        match = re.match(r"^(\d)$", grade_label)
        if match:
            grade = int(match.group(1))
            if grade < 1 or grade > 3:
                return None
    
    if grade is None:
        return None
    
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
    grade_label = row.get("grade_label", "").strip()
    
    if graduation_year:
        try:
            year = int(graduation_year)
            if year < 2000 or year > 2100:
                errors.append("graduation_year must be between 2000 and 2100")
            else:
                cleaned["graduation_year"] = year
                cleaned["graduation_year_source"] = GraduationYearSource.CSV
        except ValueError:
            errors.append("graduation_year must be a valid integer")
    elif grade_label:
        estimated = estimate_graduation_year_from_grade(grade_label)
        if estimated:
            cleaned["graduation_year"] = estimated
            cleaned["graduation_year_source"] = GraduationYearSource.ESTIMATED
        else:
            errors.append(f"could not estimate graduation_year from grade_label: {grade_label}")
    else:
        errors.append("graduation_year or grade_label is required")
    
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
    estimated_count = 0
    errors = []
    
    reader = csv.DictReader(io.StringIO(csv_content))
    
    for row_num, row in enumerate(reader, start=2):
        is_valid, cleaned, row_errors = validate_row(row, row_num)
        
        if not is_valid:
            errors.append({"row": row_num, "errors": row_errors, "data": row})
            continue
        
        if cleaned.get("graduation_year_source") == GraduationYearSource.ESTIMATED:
            estimated_count += 1
        
        existing = db.execute(
            select(Lead).where(Lead.email == cleaned["email"])
        ).scalar_one_or_none()
        
        if existing:
            existing.name = cleaned["name"]
            existing.school_name = cleaned["school_name"]
            existing.graduation_year = cleaned["graduation_year"]
            existing.graduation_year_source = cleaned.get(
                "graduation_year_source", GraduationYearSource.CSV
            )
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
        meta={
            "added": added,
            "updated": updated,
            "error_count": len(errors),
            "estimated_graduation_year_count": estimated_count
        }
    )
    
    return CSVImportResult(
        added=added,
        updated=updated,
        errors=errors,
        total_processed=added + updated + len(errors)
    )
