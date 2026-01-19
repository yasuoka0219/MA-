"""UI CSV Import endpoint with file upload and progress display"""
import io
import json
from typing import Optional
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User
from src.ma_tool.config import settings
from src.ma_tool.api.endpoints.ui_auth import get_base_context
from src.ma_tool.services.csv_import import dry_run_import, execute_import
from src.ma_tool.services.audit import log_action

router = APIRouter(prefix="/ui", tags=["UI Import"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def require_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None, RedirectResponse(url="/ui/login", status_code=302)
    return user, None


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    
    return templates.TemplateResponse("ui_import.html", {
        **get_base_context(request, user),
        "step": "upload",
        "preview": None,
        "result": None,
    })


@router.post("/import/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    
    content_bytes = await file.read()
    
    try:
        content = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            content = content_bytes.decode('cp932')
        except UnicodeDecodeError:
            return templates.TemplateResponse("ui_import.html", {
                **get_base_context(request, user),
                "step": "upload",
                "error": "ファイルの文字コードを認識できませんでした（UTF-8またはShift_JIS/cp932をサポートしています）",
                "preview": None,
                "result": None,
            })
    
    try:
        preview = dry_run_import(content)
    except Exception as e:
        return templates.TemplateResponse("ui_import.html", {
            **get_base_context(request, user),
            "step": "upload",
            "error": f"CSVの解析に失敗しました: {str(e)}",
            "preview": None,
            "result": None,
        })
    
    return templates.TemplateResponse("ui_import.html", {
        **get_base_context(request, user),
        "step": "preview",
        "preview": preview,
        "result": None,
        "session_id": preview.session_id,
    })


@router.post("/import/confirm", response_class=HTMLResponse)
async def import_confirm(
    request: Request,
    session_id: str = Form(...),
    db: Session = Depends(get_db)
):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    
    try:
        result = execute_import(db, session_id, user)
    except KeyError:
        return templates.TemplateResponse("ui_import.html", {
            **get_base_context(request, user),
            "step": "upload",
            "error": "セッションが期限切れです。もう一度CSVをアップロードしてください。",
            "preview": None,
            "result": None,
        })
    except Exception as e:
        return templates.TemplateResponse("ui_import.html", {
            **get_base_context(request, user),
            "step": "upload",
            "error": f"インポート中にエラーが発生しました: {str(e)}",
            "preview": None,
            "result": None,
        })
    
    log_action(
        db, user, "import_csv", "leads", None,
        {"added": result.added_count, "updated": result.updated_count, "errors": result.error_count}
    )
    
    response = templates.TemplateResponse("ui_import.html", {
        **get_base_context(request, user),
        "step": "result",
        "preview": None,
        "result": result,
    })
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {
            "type": "success" if result.error_count == 0 else "warning",
            "message": f"インポート完了: 追加 {result.added_count}件、更新 {result.updated_count}件"
            + (f"、エラー {result.error_count}件" if result.error_count > 0 else "")
        }
    })
    return response
