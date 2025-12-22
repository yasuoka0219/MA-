"""Seed data for Step2 scenario testing"""
import random
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.user import User, UserRole
from src.ma_tool.models.lead import Lead, GraduationYearSource
from src.ma_tool.models.event import Event
from src.ma_tool.models.template import Template, TemplateStatus
from src.ma_tool.models.scenario import Scenario

JST = ZoneInfo("Asia/Tokyo")

FIRST_NAMES = ["太郎", "花子", "健太", "美咲", "翔太", "陽菜", "大輝", "結衣", "拓海", "さくら"]
LAST_NAMES = ["田中", "山田", "佐藤", "鈴木", "高橋", "伊藤", "渡辺", "中村", "小林", "加藤"]
SCHOOLS = ["東京高校", "大阪高校", "名古屋高校", "福岡高校", "札幌高校", "横浜高校", "京都高校", "神戸高校", "仙台高校", "広島高校"]
INTERESTS = ["工学部", "理学部", "文学部", "経済学部", "法学部", "医学部", "教育学部", "農学部", "薬学部", "芸術学部"]
EVENT_TYPES = ["OC", "資料請求", "説明会", "体験授業", "相談会"]


def seed_step2_data():
    db = SessionLocal()
    
    try:
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if not admin:
            admin = User(
                email="admin@university.ac.jp",
                name="管理者",
                role=UserRole.ADMIN
            )
            db.add(admin)
            db.flush()
            print("Created admin user")
        
        templates = []
        template_data = [
            {
                "name": "OC事前案内",
                "subject": "【重要】オープンキャンパスまであと7日！{{name}}さん",
                "body_html": """
                <html><body>
                <h1>{{name}}さん、オープンキャンパスのご案内</h1>
                <p>当日のスケジュールをご確認ください。</p>
                <p>皆様のご参加をお待ちしております。</p>
                </body></html>
                """
            },
            {
                "name": "OC参加お礼",
                "subject": "{{name}}さん、ご参加ありがとうございました！",
                "body_html": """
                <html><body>
                <h1>オープンキャンパスへのご参加ありがとうございました</h1>
                <p>{{name}}さん、先日はお忙しい中ご参加いただきありがとうございました。</p>
                <p>ご質問がございましたらお気軽にお問い合わせください。</p>
                </body></html>
                """
            },
            {
                "name": "資料請求お礼",
                "subject": "資料をお送りしました - {{name}}さん",
                "body_html": """
                <html><body>
                <h1>資料請求ありがとうございます</h1>
                <p>{{name}}さん、資料をお送りしました。</p>
                <p>到着まで3〜5日程度お待ちください。</p>
                </body></html>
                """
            }
        ]
        
        for data in template_data:
            existing = db.query(Template).filter(Template.name == data["name"]).first()
            if not existing:
                template = Template(
                    name=data["name"],
                    subject=data["subject"],
                    body_html=data["body_html"],
                    status=TemplateStatus.APPROVED,
                    created_by=admin.id,
                    approved_by=admin.id,
                    approved_at=datetime.now(JST)
                )
                db.add(template)
                templates.append(template)
        
        db.flush()
        print(f"Created {len(templates)} templates")
        
        templates = list(db.query(Template).filter(Template.status == TemplateStatus.APPROVED).all())
        
        scenarios_data = [
            {
                "name": "OC事前案内（7日前）",
                "trigger_event_type": "OC",
                "delay_days": -7,
                "frequency_days": 30,
                "graduation_year_rule": json.dumps({"type": "all"}),
                "template_name": "OC事前案内"
            },
            {
                "name": "OCお礼（翌日）",
                "trigger_event_type": "OC",
                "delay_days": 1,
                "frequency_days": 7,
                "graduation_year_rule": json.dumps({"type": "all"}),
                "template_name": "OC参加お礼"
            },
            {
                "name": "資料請求お礼（即日）",
                "trigger_event_type": "資料請求",
                "delay_days": 0,
                "frequency_days": 14,
                "graduation_year_rule": json.dumps({"type": "in", "values": [2026, 2027, 2028]}),
                "template_name": "資料請求お礼"
            }
        ]
        
        created_scenarios = 0
        for data in scenarios_data:
            existing = db.query(Scenario).filter(Scenario.name == data["name"]).first()
            if not existing:
                template = next((t for t in templates if t.name == data["template_name"]), templates[0] if templates else None)
                if template:
                    scenario = Scenario(
                        name=data["name"],
                        trigger_event_type=data["trigger_event_type"],
                        delay_days=data["delay_days"],
                        frequency_days=data["frequency_days"],
                        graduation_year_rule=data["graduation_year_rule"],
                        template_id=template.id,
                        is_enabled=True
                    )
                    db.add(scenario)
                    created_scenarios += 1
        
        db.flush()
        print(f"Created {created_scenarios} scenarios")
        
        leads = []
        existing_leads = db.query(Lead).count()
        leads_to_create = max(0, 100 - existing_leads)
        
        for i in range(leads_to_create):
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            name = f"{last_name}{first_name}"
            email = f"student{existing_leads + i + 1}@example.com"
            
            consent = random.random() < 0.9
            unsubscribed = random.random() < 0.1 if consent else False
            
            lead = Lead(
                email=email,
                name=name,
                school_name=random.choice(SCHOOLS),
                graduation_year=random.choice([2026, 2027, 2028]),
                graduation_year_source=GraduationYearSource.CSV,
                interest_tags=random.choice(INTERESTS),
                consent=consent,
                unsubscribed=unsubscribed
            )
            db.add(lead)
            leads.append(lead)
        
        db.flush()
        print(f"Created {len(leads)} leads (total: {existing_leads + len(leads)})")
        
        all_leads = list(db.query(Lead).all())
        
        now = datetime.now(JST)
        events_created = 0
        for _ in range(min(50, len(all_leads))):
            lead = random.choice(all_leads)
            event_type = random.choice(EVENT_TYPES)
            
            event_date = now + timedelta(days=random.randint(-3, 14))
            
            event = Event(
                lead_id=lead.id,
                type=event_type,
                event_date=event_date
            )
            db.add(event)
            events_created += 1
        
        db.commit()
        print(f"Created {events_created} events")
        
        print("\n=== Seed Data Summary ===")
        print(f"Templates: {db.query(Template).count()}")
        print(f"Scenarios: {db.query(Scenario).filter(Scenario.is_enabled == True).count()}")
        print(f"Leads (total): {db.query(Lead).count()}")
        print(f"  - consent=true: {db.query(Lead).filter(Lead.consent == True).count()}")
        print(f"  - unsubscribed=true: {db.query(Lead).filter(Lead.unsubscribed == True).count()}")
        print(f"Events: {db.query(Event).count()}")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_step2_data()
