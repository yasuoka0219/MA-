"""デモ用: 各温度帯の見た目確認用リードを投入・更新する（本番でも管理者のみ実行）"""
from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ma_tool.models.lead import Lead, GraduationYearSource

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

    db.commit()
    return created, updated
