"""CSV import endpoint"""
from fastapi import APIRouter, UploadFile, File, HTTPException

from src.ma_tool.api.deps import CurrentUser, DbSession
from src.ma_tool.services.csv_import import import_csv
from src.ma_tool.schemas.lead import CSVImportResult

router = APIRouter()


@router.post("/import/csv", response_model=CSVImportResult)
async def import_csv_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...)
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    try:
        csv_content = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_content = content.decode("shift-jis")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Unable to decode CSV file")
    
    result = import_csv(db=db, csv_content=csv_content, actor=current_user)
    
    return result
