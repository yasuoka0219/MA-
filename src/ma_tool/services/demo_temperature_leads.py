"""デモ用: 各温度帯の見た目確認用リードを投入・更新する（本番でも管理者のみ実行）"""
from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.ma_tool.models.lead import Lead, GraduationYearSource
from src.ma_tool.models.engagement_event import EngagementEvent

# example.com は送信テスト用ドメインとして一般的。メール誤送信リスクを下げる
_DEMO_ROWS: tuple[tuple[str, str, int, str, str], ...] = (
    ("ma-demo-cold@example.com", "【デモ】Cold", 0, "cold", "DEMO_COLD"),
    ("ma-demo-warm@example.com", "【デモ】Warm", 3, "warm", "DEMO_WARM"),
    ("ma-demo-hot@example.com", "【デモ】Hot", 8, "hot", "DEMO_HOT"),
    ("ma-demo-superhot@example.com", "【デモ】Super Hot", 20, "super_hot", "DEMO_SUPER_HOT"),
)


def seed_demo_temperature_leads(db: Session) -> Tuple[int, int]:
    """
    メールアドレスで冪等に upsert。戻り値: (新規件数, 更新件数)
    """
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for email, name, score, band, ext_id in _DEMO_ROWS:
        existing = db.execute(select(Lead).where(Lead.email == email)).scalar_one_or_none()
        if existing:
            existing.name = name
            existing.engagement_score = score
            existing.score_band = band
            existing.external_id = ext_id
            existing.consent = True
            existing.unsubscribed = False
            existing.updated_at = now
            updated += 1
        else:
            lead = Lead(
                email=email,
                name=name,
                school_name="デモ高校",
                graduation_year=2026,
                graduation_year_source=GraduationYearSource.CSV,
                interest_tags="デモ",
                consent=True,
                unsubscribed=False,
                engagement_score=score,
                score_band=band,
                external_id=ext_id,
            )
            db.add(lead)
            created += 1

    # リスト画面の「ステータス」確認用ダミーイベントを冪等に再作成
    demo_emails = [row[0] for row in _DEMO_ROWS]
    demo_leads = db.execute(select(Lead).where(Lead.email.in_(demo_emails))).scalars().all()
    demo_ids = [lead.id for lead in demo_leads]
    if demo_ids:
        db.execute(delete(EngagementEvent).where(EngagementEvent.lead_id.in_(demo_ids)))
        lead_by_email = {lead.email: lead for lead in demo_leads}

        warm_lead = lead_by_email.get("ma-demo-warm@example.com")
        if warm_lead:
            db.add(EngagementEvent(
                lead_id=warm_lead.id,
                event_type="open",
                occurred_at=now,
            ))

        hot_lead = lead_by_email.get("ma-demo-hot@example.com")
        if hot_lead:
            db.add(EngagementEvent(
                lead_id=hot_lead.id,
                event_type="click",
                url="https://example.com/campus-life",
                occurred_at=now,
            ))

        super_hot_lead = lead_by_email.get("ma-demo-superhot@example.com")
        if super_hot_lead:
            db.add(EngagementEvent(
                lead_id=super_hot_lead.id,
                event_type="page_view",
                url="https://example.com/apply",
                occurred_at=now,
            ))

    db.commit()
    return created, updated
