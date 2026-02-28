"""UI endpoints for lead management"""
import csv
import io
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_, func
from email_validator import validate_email, EmailNotValidError

from src.ma_tool.database import get_db
from src.ma_tool.models.lead import Lead, GraduationYearSource
from src.ma_tool.models.line_identity import LineIdentity, LineIdentityStatus
from src.ma_tool.models.send_log import SendLog, SendStatus
from src.ma_tool.models.scenario import Scenario
from src.ma_tool.models.engagement_event import EngagementEvent
from src.ma_tool.models.user import User
from src.ma_tool.api.deps import require_session_login
from src.ma_tool.config import settings

JST = ZoneInfo("Asia/Tokyo")

router = APIRouter(prefix="/ui", tags=["UI Leads"])
templates = Jinja2Templates(directory="src/ma_tool/templates")


def get_base_context(request: Request, user: User):
    return {
        "request": request,
        "current_user": user,
        "app_env": settings.APP_ENV,
        "is_production": settings.is_production,
    }


def get_lead_engagement_statuses(db: Session, lead_ids: list[int]) -> dict[int, str]:
    """
    リードIDのリストに対して、エンゲージメントステータスを一括取得する。
    返す値: "important_page" | "click" | "page_view" | "open" | "none"
    """
    if not lead_ids:
        return {}

    result = {lid: "none" for lid in lead_ids}
    important_paths = getattr(settings, "important_page_list", []) or []

    # 重要ページPVあり: event_type=page_view かつ url が重要パスを含む
    if important_paths:
        path_conds = or_(*[EngagementEvent.url.ilike(f"%{p.strip()}%") for p in important_paths if p.strip()])
        q = select(EngagementEvent.lead_id).where(
            and_(
                EngagementEvent.lead_id.in_(lead_ids),
                EngagementEvent.lead_id.isnot(None),
                EngagementEvent.event_type == "page_view",
                path_conds,
            )
        ).distinct()
        for (lead_id,) in db.execute(q).all():
            if lead_id and result.get(lead_id) == "none":
                result[lead_id] = "important_page"

    # クリックあり
    q = select(EngagementEvent.lead_id).where(
        and_(
            EngagementEvent.lead_id.in_(lead_ids),
            EngagementEvent.lead_id.isnot(None),
            EngagementEvent.event_type == "click",
        )
    ).distinct()
    for (lead_id,) in db.execute(q).all():
        if lead_id and result.get(lead_id) == "none":
            result[lead_id] = "click"

    # サイト訪問あり（PV）
    q = select(EngagementEvent.lead_id).where(
        and_(
            EngagementEvent.lead_id.in_(lead_ids),
            EngagementEvent.lead_id.isnot(None),
            EngagementEvent.event_type == "page_view",
        )
    ).distinct()
    for (lead_id,) in db.execute(q).all():
        if lead_id and result.get(lead_id) == "none":
            result[lead_id] = "page_view"

    # 開封済み（SendLog.opened_at が入っている送信が1件以上）
    q = select(SendLog.lead_id).where(
        and_(
            SendLog.lead_id.in_(lead_ids),
            SendLog.opened_at.isnot(None),
        )
    ).distinct()
    for (lead_id,) in db.execute(q).all():
        if lead_id and result.get(lead_id) == "none":
            result[lead_id] = "open"

    return result


def build_lead_query(
    db: Session,
    search: Optional[str] = None,
    graduation_year: Optional[int] = None,
    interest: Optional[str] = None,
    unsubscribed_filter: Optional[str] = None,
):
    """リード検索クエリを構築（一覧表示とエクスポートで共通使用）"""
    query = select(Lead)
    
    if search:
        query = query.where(
            or_(
                Lead.email.ilike(f"%{search}%"),
                Lead.school_name.ilike(f"%{search}%"),
                Lead.name.ilike(f"%{search}%"),
            )
        )
    if graduation_year:
        query = query.where(Lead.graduation_year == graduation_year)
    if interest:
        query = query.where(Lead.interest_tags.ilike(f"%{interest}%"))
    if unsubscribed_filter == "true":
        query = query.where(Lead.unsubscribed == True)
    elif unsubscribed_filter == "false":
        query = query.where(Lead.unsubscribed == False)
    
    return query.order_by(Lead.created_at.desc())


@router.get("/leads", response_class=HTMLResponse)
async def leads_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    search: Optional[str] = Query(None),
    graduation_year: Optional[int] = Query(None),
    interest: Optional[str] = Query(None),
    unsubscribed_filter: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    query = build_lead_query(db, search, graduation_year, interest, unsubscribed_filter)
    
    per_page = 50
    offset = (page - 1) * per_page
    
    # フィルタ適用後の総件数を取得
    total_count = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    
    leads = db.execute(query.offset(offset).limit(per_page)).scalars().all()
    
    lead_ids = [l.id for l in leads]
    line_identities = {}
    if lead_ids:
        identities = db.execute(
            select(LineIdentity).where(LineIdentity.lead_id.in_(lead_ids))
        ).scalars().all()
        for identity in identities:
            line_identities[identity.lead_id] = identity

    lead_statuses = get_lead_engagement_statuses(db, lead_ids)
    
    graduation_years = db.execute(
        select(Lead.graduation_year).distinct().where(Lead.graduation_year.isnot(None)).order_by(Lead.graduation_year.desc())
    ).scalars().all()
    
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    start_item = (page - 1) * per_page + 1 if total_count > 0 else 0
    end_item = min(page * per_page, total_count)
    
    return templates.TemplateResponse("ui_leads_list.html", {
        **get_base_context(request, user),
        "leads": leads,
        "line_identities": line_identities,
        "lead_statuses": lead_statuses,
        "search": search or "",
        "graduation_year": graduation_year,
        "interest": interest or "",
        "unsubscribed_filter": unsubscribed_filter or "",
        "page": page,
        "total_count": total_count,
        "per_page": per_page,
        "total_pages": total_pages,
        "start_item": start_item,
        "end_item": end_item,
        "graduation_years": graduation_years,
        "message": message,
        "error": error,
    })


@router.get("/leads/new", response_class=HTMLResponse)
async def lead_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    return templates.TemplateResponse("ui_lead_form.html", {
        **get_base_context(request, user),
        "lead": None,
        "is_new": True,
    })


@router.post("/leads/new")
async def lead_create(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    school_name: Optional[str] = Form(None),
    graduation_year: Optional[int] = Form(None),
    grade_label: Optional[str] = Form(None),
    interest_tags: Optional[str] = Form(None),
    external_id: Optional[str] = Form(None),
    consent: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    # メールアドレスのバリデーション
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
        email = validated_email.email
    except EmailNotValidError as e:
        return templates.TemplateResponse("ui_lead_form.html", {
            **get_base_context(request, user),
            "lead": None,
            "is_new": True,
            "error": f"メールアドレスの形式が不正です: {str(e)}",
            "form_data": {
                "email": email,
                "name": name,
                "school_name": school_name,
                "graduation_year": graduation_year,
                "grade_label": grade_label,
                "interest_tags": interest_tags,
                "external_id": external_id,
                "consent": consent,
            }
        })
    
    # メールアドレスの重複チェック
    existing = db.execute(select(Lead).where(Lead.email == email)).scalar_one_or_none()
    if existing:
        return templates.TemplateResponse("ui_lead_form.html", {
            **get_base_context(request, user),
            "lead": None,
            "is_new": True,
            "error": f"このメールアドレスは既に登録されています（ID: {existing.id}）",
            "form_data": {
                "email": email,
                "name": name,
                "school_name": school_name,
                "graduation_year": graduation_year,
                "grade_label": grade_label,
                "interest_tags": interest_tags,
                "external_id": external_id,
                "consent": consent,
            }
        })
    
    # 卒業年度の計算
    graduation_year_final = graduation_year
    graduation_year_source = GraduationYearSource.CSV
    
    if not graduation_year_final and grade_label:
        from src.ma_tool.services.csv_normalizer import normalize_grade_label
        grade_num = normalize_grade_label(grade_label)
        if grade_num:
            from src.ma_tool.services.csv_import import estimate_graduation_year_from_grade
            graduation_year_final = estimate_graduation_year_from_grade(grade_num)
            graduation_year_source = GraduationYearSource.ESTIMATED
    
    if not graduation_year_final:
        # デフォルト値として現在年度+3年を設定
        today = datetime.now()
        if today.month >= 4:
            graduation_year_final = today.year + 3
        else:
            graduation_year_final = today.year + 2
        graduation_year_source = GraduationYearSource.ESTIMATED
    
    lead = Lead(
        email=email,
        name=name.strip(),
        school_name=school_name.strip() if school_name else None,
        graduation_year=graduation_year_final,
        graduation_year_source=graduation_year_source,
        interest_tags=interest_tags.strip() if interest_tags else None,
        external_id=external_id.strip() if external_id else None,
        consent=consent,
    )
    
    db.add(lead)
    db.commit()
    db.refresh(lead)
    
    response = RedirectResponse(url=f"/ui/leads/{lead.id}?message=リードを登録しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "リードを登録しました", "type": "success"}})
    return response


@router.get("/leads/export", response_class=Response)
async def leads_export(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    search: Optional[str] = Query(None),
    graduation_year: Optional[int] = Query(None),
    interest: Optional[str] = Query(None),
    unsubscribed_filter: Optional[str] = Query(None),
):
    """リード一覧をCSV形式でエクスポート"""
    query = build_lead_query(db, search, graduation_year, interest, unsubscribed_filter)
    leads = db.execute(query).scalars().all()
    
    # LINE連携情報を取得
    lead_ids = [l.id for l in leads]
    line_identities = {}
    if lead_ids:
        identities = db.execute(
            select(LineIdentity).where(LineIdentity.lead_id.in_(lead_ids))
        ).scalars().all()
        for identity in identities:
            line_identities[identity.lead_id] = identity
    
    # CSV生成
    output = io.StringIO()
    writer = csv.writer(output)
    
    # ヘッダー行
    writer.writerow([
        "ID",
        "外部ID",
        "メールアドレス",
        "名前",
        "学校名",
        "卒業年度",
        "卒業年度ソース",
        "興味関心タグ",
        "同意",
        "配信停止",
        "LINEブロック",
        "LINE連携",
        "作成日時",
        "更新日時",
    ])
    
    # データ行
    for lead in leads:
        line_identity = line_identities.get(lead.id)
        line_status = ""
        if line_identity:
            if line_identity.status == LineIdentityStatus.LINKED:
                line_status = "紐付け済"
            elif line_identity.status == LineIdentityStatus.BLOCKED:
                line_status = "ブロック"
            else:
                line_status = "未紐付け"
        
        writer.writerow([
            lead.id,
            lead.external_id or "",
            lead.email,
            lead.name,
            lead.school_name or "",
            lead.graduation_year,
            lead.graduation_year_source.value,
            lead.interest_tags or "",
            "はい" if lead.consent else "いいえ",
            "はい" if lead.unsubscribed else "いいえ",
            "はい" if lead.line_blocked else "いいえ",
            line_status,
            lead.created_at.strftime('%Y-%m-%d %H:%M:%S') if lead.created_at else "",
            lead.updated_at.strftime('%Y-%m-%d %H:%M:%S') if lead.updated_at else "",
        ])
    
    # ファイル名に日時を含める
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"leads_export_{timestamp}.csv"
    
    # UTF-8 BOM付きで返す（Excelで開きやすくするため）
    csv_content = output.getvalue()
    csv_bytes = csv_content.encode('utf-8-sig')
    
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/leads/{lead_id}/edit", response_class=HTMLResponse)
async def lead_edit(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<h1>リードが見つかりません</h1>", status_code=404)
    
    # 卒業年度から学年を推定（表示用）
    estimated_grade = None
    if lead.graduation_year:
        today = datetime.now()
        if today.month >= 4:
            school_year_start = today.year
        else:
            school_year_start = today.year - 1
        
        years_until_graduation = lead.graduation_year - school_year_start
        if 1 <= years_until_graduation <= 3:
            estimated_grade = f"高{years_until_graduation}"
    
    return templates.TemplateResponse("ui_lead_form.html", {
        **get_base_context(request, user),
        "lead": lead,
        "is_new": False,
        "estimated_grade": estimated_grade,
    })


@router.post("/leads/{lead_id}/edit")
async def lead_update(
    request: Request,
    lead_id: int,
    email: str = Form(...),
    name: str = Form(...),
    school_name: Optional[str] = Form(None),
    graduation_year: Optional[int] = Form(None),
    grade_label: Optional[str] = Form(None),
    interest_tags: Optional[str] = Form(None),
    external_id: Optional[str] = Form(None),
    consent: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<h1>リードが見つかりません</h1>", status_code=404)
    
    # メールアドレスのバリデーション
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
        email = validated_email.email
    except EmailNotValidError as e:
        return templates.TemplateResponse("ui_lead_form.html", {
            **get_base_context(request, user),
            "lead": lead,
            "is_new": False,
            "error": f"メールアドレスの形式が不正です: {str(e)}",
        })
    
    # メールアドレスの重複チェック（自分以外）
    existing = db.execute(select(Lead).where(Lead.email == email, Lead.id != lead_id)).scalar_one_or_none()
    if existing:
        return templates.TemplateResponse("ui_lead_form.html", {
            **get_base_context(request, user),
            "lead": lead,
            "is_new": False,
            "error": f"このメールアドレスは既に登録されています（ID: {existing.id}）",
        })
    
    # 卒業年度の計算
    graduation_year_final = graduation_year
    graduation_year_source = lead.graduation_year_source
    
    if not graduation_year_final and grade_label:
        from src.ma_tool.services.csv_normalizer import normalize_grade_label
        grade_num = normalize_grade_label(grade_label)
        if grade_num:
            from src.ma_tool.services.csv_import import estimate_graduation_year_from_grade
            graduation_year_final = estimate_graduation_year_from_grade(grade_num)
            graduation_year_source = GraduationYearSource.ESTIMATED
    
    if not graduation_year_final:
        graduation_year_final = lead.graduation_year
    
    lead.email = email
    lead.name = name.strip()
    lead.school_name = school_name.strip() if school_name else None
    lead.graduation_year = graduation_year_final
    lead.graduation_year_source = graduation_year_source
    lead.interest_tags = interest_tags.strip() if interest_tags else None
    lead.external_id = external_id.strip() if external_id else None
    lead.consent = consent
    lead.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(lead)
    
    response = RedirectResponse(url=f"/ui/leads/{lead.id}?message=リードを更新しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "リードを更新しました", "type": "success"}})
    return response


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
    message: Optional[str] = Query(None),
):
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<h1>リードが見つかりません</h1>", status_code=404)
    
    line_identity = db.execute(
        select(LineIdentity).where(LineIdentity.lead_id == lead_id)
    ).scalar_one_or_none()
    
    # 送信履歴を取得（最新20件）
    send_logs = db.execute(
        select(SendLog)
        .where(SendLog.lead_id == lead_id)
        .order_by(SendLog.created_at.desc())
        .limit(20)
    ).scalars().all()
    
    scenario_ids = list(set([log.scenario_id for log in send_logs]))
    scenarios = {}
    if scenario_ids:
        scenario_list = db.execute(
            select(Scenario).where(Scenario.id.in_(scenario_ids))
        ).scalars().all()
        for scenario in scenario_list:
            scenarios[scenario.id] = scenario

    now = datetime.now(JST)
    seven_days_ago = now - timedelta(days=7)

    engagement_events = db.execute(
        select(EngagementEvent)
        .where(EngagementEvent.lead_id == lead_id)
        .order_by(EngagementEvent.occurred_at.desc())
        .limit(50)
    ).scalars().all()

    pv_7d = db.execute(
        select(func.count()).select_from(EngagementEvent)
        .where(and_(
            EngagementEvent.lead_id == lead_id,
            EngagementEvent.event_type == "page_view",
            EngagementEvent.occurred_at >= seven_days_ago,
        ))
    ).scalar() or 0

    click_count = db.execute(
        select(func.count()).select_from(EngagementEvent)
        .where(and_(
            EngagementEvent.lead_id == lead_id,
            EngagementEvent.event_type == "click",
        ))
    ).scalar() or 0

    important_pages = settings.important_page_list
    important_pv_count = 0
    if important_pages:
        for page_url in important_pages:
            important_pv_count += db.execute(
                select(func.count()).select_from(EngagementEvent)
                .where(and_(
                    EngagementEvent.lead_id == lead_id,
                    EngagementEvent.event_type.in_(["click", "page_view"]),
                    EngagementEvent.url.ilike(f"%{page_url}%"),
                ))
            ).scalar() or 0

    return templates.TemplateResponse("ui_lead_detail.html", {
        **get_base_context(request, user),
        "lead": lead,
        "line_identity": line_identity,
        "send_logs": send_logs,
        "scenarios": scenarios,
        "message": message,
        "engagement_events": engagement_events,
        "pv_7d": pv_7d,
        "click_count": click_count,
        "important_pv_count": important_pv_count,
    })


@router.post("/leads/{lead_id}/unsubscribe")
async def lead_unsubscribe(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """リードの配信を停止"""
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<h1>リードが見つかりません</h1>", status_code=404)
    
    lead.unsubscribed = True
    lead.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    # 監査ログに記録
    from src.ma_tool.services.audit import log_action
    log_action(
        db=db,
        actor=user,
        action="LEAD_UNSUBSCRIBED",
        target_type="lead",
        target_id=lead.id,
        meta={"email": lead.email, "source": "admin_ui"}
    )
    
    response = RedirectResponse(url=f"/ui/leads/{lead.id}?message=配信を停止しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "配信を停止しました", "type": "success"}})
    return response


@router.post("/leads/{lead_id}/resubscribe")
async def lead_resubscribe(
    request: Request,
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """リードの配信を再開"""
    lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
    if not lead:
        return HTMLResponse("<h1>リードが見つかりません</h1>", status_code=404)
    
    lead.unsubscribed = False
    lead.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    # 監査ログに記録
    from src.ma_tool.services.audit import log_action
    log_action(
        db=db,
        actor=user,
        action="LEAD_RESUBSCRIBED",
        target_type="lead",
        target_id=lead.id,
        meta={"email": lead.email, "source": "admin_ui"}
    )
    
    response = RedirectResponse(url=f"/ui/leads/{lead.id}?message=配信を再開しました", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "配信を再開しました", "type": "success"}})
    return response


@router.post("/leads/bulk-action")
async def leads_bulk_action(
    request: Request,
    action: str = Form(...),
    lead_ids: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_session_login),
):
    """リードのバルク操作（削除、配信停止、配信再開）"""
    from src.ma_tool.services.audit import log_action
    
    # lead_idsをパース
    try:
        ids = [int(id_str.strip()) for id_str in lead_ids.split(",") if id_str.strip()]
    except ValueError:
        response = RedirectResponse(url="/ui/leads?error=無効なリードIDが含まれています", status_code=302)
        response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "無効なリードIDが含まれています", "type": "error"}})
        return response
    
    if not ids:
        response = RedirectResponse(url="/ui/leads?error=リードが選択されていません", status_code=302)
        response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "リードが選択されていません", "type": "error"}})
        return response
    
    # リードを取得
    leads = db.execute(select(Lead).where(Lead.id.in_(ids))).scalars().all()
    
    if not leads:
        response = RedirectResponse(url="/ui/leads?error=リードが見つかりません", status_code=302)
        response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "リードが見つかりません", "type": "error"}})
        return response
    
    success_count = 0
    now = datetime.now(timezone.utc)
    
    if action == "delete":
        # バルク削除
        for lead in leads:
            db.delete(lead)
            success_count += 1
        
        db.commit()
        
        # 監査ログに記録
        log_action(
            db=db,
            actor=user,
            action="LEAD_BULK_DELETED",
            target_type="lead",
            meta={"count": success_count, "lead_ids": ids}
        )
        
        message = f"{success_count}件のリードを削除しました"
        
    elif action == "unsubscribe":
        # バルク配信停止
        for lead in leads:
            if not lead.unsubscribed:
                lead.unsubscribed = True
                lead.updated_at = now
                success_count += 1
        
        db.commit()
        
        # 監査ログに記録
        log_action(
            db=db,
            actor=user,
            action="LEAD_BULK_UNSUBSCRIBED",
            target_type="lead",
            meta={"count": success_count, "lead_ids": ids}
        )
        
        message = f"{success_count}件のリードの配信を停止しました"
        
    elif action == "resubscribe":
        # バルク配信再開
        for lead in leads:
            if lead.unsubscribed:
                lead.unsubscribed = False
                lead.updated_at = now
                success_count += 1
        
        db.commit()
        
        # 監査ログに記録
        log_action(
            db=db,
            actor=user,
            action="LEAD_BULK_RESUBSCRIBED",
            target_type="lead",
            meta={"count": success_count, "lead_ids": ids}
        )
        
        message = f"{success_count}件のリードの配信を再開しました"
        
    else:
        response = RedirectResponse(url="/ui/leads?error=無効な操作です", status_code=302)
        response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": "無効な操作です", "type": "error"}})
        return response
    
    response = RedirectResponse(url=f"/ui/leads?message={message}", status_code=302)
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": "success"}})
    return response
