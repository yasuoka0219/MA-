"""CSV import endpoints with preview and confirmation workflow"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os

from src.ma_tool.api.deps import CurrentUser, DbSession
from src.ma_tool.services.csv_import import (
    decode_csv_content,
    dry_run_import,
    execute_import,
    IMPORT_SESSIONS,
    auto_map_columns,
)
from src.ma_tool.schemas.csv_import import (
    DryRunResult,
    ImportResult,
    ImportConfirmRequest,
)
from src.ma_tool.schemas.lead import CSVImportResult

router = APIRouter()


@router.post("/import/preview", response_model=DryRunResult)
async def preview_csv_import(
    file: UploadFile = File(...)
):
    """
    Preview CSV import with dry-run.
    Returns mapping suggestions, validation results, and first 20 rows preview.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    try:
        csv_content = decode_csv_content(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    result = dry_run_import(csv_content)
    
    return result


@router.post("/import/confirm", response_model=ImportResult)
async def confirm_csv_import(
    db: DbSession,
    current_user: CurrentUser,
    request: ImportConfirmRequest
):
    """
    Execute the CSV import after preview.
    Optionally accepts updated column mappings.
    """
    if request.session_id not in IMPORT_SESSIONS:
        raise HTTPException(
            status_code=400, 
            detail="Invalid or expired session. Please run preview again."
        )
    
    updated_mapping = None
    if request.column_mappings:
        updated_mapping = {
            cm.original: cm.mapped_to 
            for cm in request.column_mappings 
            if cm.mapped_to
        }
    
    try:
        result = execute_import(
            db=db,
            session_id=request.session_id,
            actor=current_user,
            updated_mapping=updated_mapping
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/import/errors/{session_id}")
async def download_error_csv(session_id: str):
    """
    Download error CSV for a completed import.
    """
    error_dir = "/tmp/csv_errors"
    filename = f"errors_{session_id[:8]}.csv"
    filepath = os.path.join(error_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Error CSV not found or expired")
    
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="text/csv"
    )


@router.post("/import/csv", response_model=CSVImportResult)
async def import_csv_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...)
):
    """
    Legacy: Direct CSV import (for backward compatibility).
    For safer imports, use /import/preview + /import/confirm workflow.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    try:
        csv_content = decode_csv_content(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    from src.ma_tool.services.csv_import import import_csv
    result = import_csv(db=db, csv_content=csv_content, actor=current_user)
    
    return result
