"""Unsubscribe endpoint"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.api.deps import DbSession
from src.ma_tool.services.unsubscribe import verify_unsubscribe_token, process_unsubscribe
from src.ma_tool.services.audit import log_action
from src.ma_tool.models.user import User

router = APIRouter()


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, db: DbSession):
    lead_id = verify_unsubscribe_token(token)
    
    if lead_id is None:
        return HTMLResponse(
            content="""
            <html>
                <head><title>配信停止 - エラー</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>リンクが無効です</h1>
                    <p>配信停止リンクの有効期限が切れているか、無効なリンクです。</p>
                </body>
            </html>
            """,
            status_code=400
        )
    
    lead = process_unsubscribe(db, lead_id)
    
    if lead is None:
        return HTMLResponse(
            content="""
            <html>
                <head><title>配信停止 - エラー</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>ユーザーが見つかりません</h1>
                    <p>該当するユーザーが見つかりませんでした。</p>
                </body>
            </html>
            """,
            status_code=404
        )
    
    system_user = db.execute(select(User).where(User.id == 1)).scalar_one_or_none()
    if system_user:
        log_action(
            db=db,
            actor=system_user,
            action="LEAD_UNSUBSCRIBED",
            target_type="lead",
            target_id=lead.id,
            meta={"email": lead.email}
        )
    
    return HTMLResponse(
        content=f"""
        <html>
            <head><title>配信停止完了</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>配信停止が完了しました</h1>
                <p>メールアドレス: {lead.email}</p>
                <p>今後、メール配信は行われません。</p>
            </body>
        </html>
        """
    )
