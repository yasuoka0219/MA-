"""CSV import schemas with preview and dry-run support"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ColumnMapping(BaseModel):
    original: str
    mapped_to: Optional[str] = None
    confidence: float = 0.0
    

class MappingPreview(BaseModel):
    columns: List[ColumnMapping]
    unmapped_columns: List[str]
    missing_required: List[str]


class RowPreview(BaseModel):
    row_number: int
    original: Dict[str, str]
    normalized: Dict[str, Any]
    errors: List[str]
    warnings: List[str]


class DryRunResult(BaseModel):
    total_rows: int
    will_add: int
    will_update: int
    will_skip: int
    error_count: int
    warning_count: int
    preview_rows: List[RowPreview]
    mapping: MappingPreview
    session_id: str


class ImportError(BaseModel):
    row_number: int
    errors: List[str]
    original_data: Dict[str, str]


class ImportResult(BaseModel):
    added: int
    updated: int
    skipped: int
    errors: List[ImportError]
    warnings: List[Dict[str, Any]]
    total_processed: int
    error_csv_available: bool = False
    error_csv_path: Optional[str] = None


class ColumnMappingUpdate(BaseModel):
    original: str
    mapped_to: Optional[str]


class ImportConfirmRequest(BaseModel):
    session_id: str
    column_mappings: Optional[List[ColumnMappingUpdate]] = None
