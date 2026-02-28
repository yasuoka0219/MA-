"""UI CSV Import endpoint with file upload and progress display"""
import csv
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

    max_bytes = settings.CSV_MAX_UPLOAD_MB * 1024 * 1024

    try:
        content_bytes = await file.read()
    except Exception as e:
        return templates.TemplateResponse("ui_import.html", {
            **get_base_context(request, user),
            "step": "upload",
            "error": "ファイルの読み込みに失敗しました。ネットワークを確認するか、ファイルを小さくして再試行してください。",
            "preview": None,
            "result": None,
        })

    if len(content_bytes) > max_bytes:
        return templates.TemplateResponse("ui_import.html", {
            **get_base_context(request, user),
            "step": "upload",
            "error": f"ファイルが大きすぎます（上限: {settings.CSV_MAX_UPLOAD_MB}MB）。分割するか、件数を減らして再度アップロードしてください。",
            "preview": None,
            "result": None,
        })

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
    
    error_count = len(result.errors)
    log_action(
        db, user, "import_csv", "leads", None,
        {"added": result.added, "updated": result.updated, "errors": error_count}
    )
    
    response = templates.TemplateResponse("ui_import.html", {
        **get_base_context(request, user),
        "step": "result",
        "preview": None,
        "result": result,
    })
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {
            "type": "success" if error_count == 0 else "warning",
            "message": f"インポート完了: 追加 {result.added}件、更新 {result.updated}件"
            + (f"、エラー {error_count}件" if error_count > 0 else "")
        }
    })
    return response


@router.get("/import/template", response_class=Response)
async def download_template(
    request: Request,
    db: Session = Depends(get_db)
):
    """CSVインポート用の見本ファイルをダウンロード"""
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    
    # CSV見本を生成
    output = io.StringIO()
    writer = csv.writer(output)
    
    # ヘッダー行（日本語名で統一）
    writer.writerow([
        "個人ID",
        "漢字氏名",
        "メールアドレス1",
        "メールアドレス2",
        "卒年",
        "学年",
        "高校正式名称",
        "興味関心タグ",
        "同意"
    ])
    
    # サンプルデータ（3行）
    writer.writerow([
        "STU001",
        "山田太郎",
        "yamada.taro@example.com",
        "",
        "2026",
        "",
        "東京都立○○高等学校",
        "情報工学部,コンピュータサイエンス",
        "はい"
    ])
    writer.writerow([
        "STU002",
        "佐藤花子",
        "sato.hanako@example.com",
        "",
        "2027",
        "",
        "神奈川県立△△高等学校",
        "経済学部",
        "はい"
    ])
    writer.writerow([
        "STU003",
        "鈴木一郎",
        "suzuki.ichiro@example.com",
        "",
        "",
        "高2",
        "埼玉県立□□高等学校",
        "法学部",
        "はい"
    ])
    
    # UTF-8 BOM付きで返す（Excelで開きやすくするため）
    csv_content = output.getvalue()
    csv_bytes = csv_content.encode('utf-8-sig')
    
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="leads_import_template.csv"'
        }
    )
