# MA Tool - 大学向けマーケティングオートメーションツール

## 概要
大学が保有する高校生/学生データ（CSV）に対して、卒業年度×イベント起点で、学年最適化したメールを自動配信するMAツールのMVP版。

## 現在の状態
- **Step1基盤** 完了
- FastAPI + PostgreSQL + SQLAlchemy 2.x + Alembic
- 個人情報保護対応（同意・配信停止・監査ログ・権限）
- メール誤送信防止（dev/staging環境でのリダイレクト制御）
- **追加機能**: 学年（grade_label）からの卒業年度推定
- **追加機能**: EmailService抽象化（非同期対応準備）

## プロジェクト構造
```
src/ma_tool/
├── main.py           # FastAPIアプリケーション
├── config.py         # 環境変数管理（Pydantic Settings）
├── database.py       # DBセッション管理
├── seed.py           # 初期データ投入
├── api/
│   ├── deps.py       # 認証・依存性注入
│   └── endpoints/
│       ├── health.py      # ヘルスチェック
│       ├── csv_import.py  # CSVインポート
│       └── unsubscribe.py # 配信停止
├── models/           # SQLAlchemyモデル
│   ├── user.py       # ユーザー（権限管理）
│   ├── lead.py       # リード（学生）+ GraduationYearSource
│   ├── event.py      # イベント
│   ├── template.py   # メールテンプレート
│   ├── scenario.py   # 配信シナリオ
│   ├── send_log.py   # 送信ログ
│   └── audit_log.py  # 監査ログ
├── schemas/          # Pydanticスキーマ
└── services/         # ビジネスロジック
    ├── audit.py      # 監査ログサービス
    ├── csv_import.py # CSVインポート（学年推定対応）
    ├── email.py      # メール送信（抽象化・誤送信防止）
    └── unsubscribe.py # 配信停止サービス
```

## 環境変数（Replit Secrets）
| 変数名 | 必須 | 説明 |
|--------|------|------|
| DATABASE_URL | ✓ | PostgreSQL接続文字列 |
| SENDGRID_API_KEY | メール送信時 | SendGrid APIキー |
| APP_ENV | - | dev/staging/prod（デフォルト: dev） |
| MAIL_FROM | - | 送信元メールアドレス |
| MAIL_REDIRECT_TO | dev/staging時必須 | 強制リダイレクト先 |
| MAIL_ALLOWLIST | - | 許可ドメイン（カンマ区切り） |
| UNSUBSCRIBE_SECRET | - | 配信停止トークン署名用 |
| TRACKING_SECRET | - | 開封計測用（Step4で使用） |

## APIエンドポイント
- `GET /` - API情報
- `GET /health` - ヘルスチェック
- `POST /import/csv` - CSVインポート
- `GET /unsubscribe/{token}` - 配信停止

## 起動手順
```bash
# マイグレーション適用
python -m alembic upgrade head

# シードデータ投入
python -m src.ma_tool.seed

# サーバー起動
python -m uvicorn src.ma_tool.main:app --host 0.0.0.0 --port 5000 --reload
```

## CSVインポート

### graduation_yearを直接指定する場合
```csv
email,name,school_name,graduation_year,interest_tags,consent
tanaka@example.com,田中太郎,東京高校,2025,経済学部,true
```

### grade_label（学年）から推定する場合
```csv
email,name,school_name,grade_label,interest_tags,consent
ito@example.com,伊藤健太,北海道高校,高1,理学部,true
watanabe@example.com,渡辺真理,大阪高校,高2,文学部,true
```

対応する学年ラベル: 高1/高2/高3, 1/2/3, 1年/2年/3年, 高校1年/高校2年/高校3年

推定されたデータは `graduation_year_source = 'ESTIMATED'` でマークされ、後から抽出可能：
```sql
SELECT * FROM leads WHERE graduation_year_source = 'ESTIMATED';
```

## メール送信アーキテクチャ

EmailServiceは抽象化されており、以下のプロバイダーに対応：
- **SendGridProvider**: 本番用（SENDGRID_API_KEYが設定されている場合）
- **MockEmailProvider**: テスト用（APIキー未設定時）

非同期化（Celery/BackgroundTasks）への対応が容易な設計：
```python
from src.ma_tool.services.email import get_email_service, EmailMessage

service = get_email_service()
result = service.send(EmailMessage(
    to_email="user@example.com",
    subject="件名",
    html_content="<p>本文</p>"
))
```

## 設計判断
1. **誤送信防止**: dev/staging環境では必ずMAIL_REDIRECT_TOにリダイレクト
2. **監査ログ**: すべての重要操作を記録（actor_role_snapshotで当時のロールを保持）
3. **認証**: MVP段階ではヘッダーベースの簡易認証（X-User-ID）
4. **二重送信防止**: send_logsテーブルでlead_id×scenario_id×scheduled_forの一意制約を想定（Step2で追加）
5. **卒業年度推定**: CSVにgraduation_yearがない場合、grade_labelから自動推定
6. **メールサービス疎結合**: Provider抽象化により将来の非同期化・プロバイダー切り替えに対応

## 最近の変更
- 2024-12-22: graduation_year_source追加、EmailService抽象化
- 2024-12: Step1基盤実装完了
