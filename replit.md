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
- **追加機能**: CSVインポート事故率低減（正規化・プレビュー・ドライラン）

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
│       ├── csv_import.py  # CSVインポート（プレビュー対応）
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
│   ├── lead.py
│   └── csv_import.py # インポートスキーマ
└── services/         # ビジネスロジック
    ├── audit.py           # 監査ログサービス
    ├── csv_normalizer.py  # 列名・値の正規化
    ├── csv_import.py      # CSVインポート（学年推定対応）
    ├── email.py           # メール送信（抽象化・誤送信防止）
    └── unsubscribe.py     # 配信停止サービス
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
- `POST /import/preview` - CSVプレビュー（ドライラン）
- `POST /import/confirm` - CSVインポート確定
- `POST /import/csv` - CSVインポート（レガシー互換）
- `GET /import/errors/{session_id}` - エラーCSVダウンロード
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

## CSVインポート（安全なワークフロー）

### 1. プレビュー（ドライラン）
```bash
curl -X POST "http://localhost:5000/import/preview" \
  -F "file=@leads.csv"
```

レスポンス例:
```json
{
  "total_rows": 100,
  "will_add": 80,
  "will_update": 15,
  "will_skip": 5,
  "error_count": 5,
  "preview_rows": [...],
  "mapping": {
    "columns": [
      {"original": "メールアドレス", "mapped_to": "email", "confidence": 1.0}
    ]
  },
  "session_id": "abc123..."
}
```

### 2. インポート確定
```bash
curl -X POST "http://localhost:5000/import/confirm" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: 1" \
  -d '{"session_id": "abc123..."}'
```

### 3. エラーCSVダウンロード（エラーがある場合）
```bash
curl "http://localhost:5000/import/errors/abc123..."
```

## 列名の自動マッピング

日本語列名を自動認識:
| 元の列名 | マッピング先 |
|---------|-------------|
| メールアドレス, mail, Eメール | email |
| 氏名, 名前, フルネーム | name |
| 高校名, 学校名, 学校 | school_name |
| 学年, year | grade_label |
| 卒業年度, 卒年 | graduation_year |
| 同意, 承諾, オプトイン | consent |
| 志望学部, 興味, タグ | interest_tags |

## 値の正規化

### 学年 (grade_label)
- 高1, 高一, 高校1年, 高校１年生, 1年, １, 一年生 → grade=1 → 卒業年度推定

### 同意 (consent)
- true, 1, yes, はい, 同意, 同意あり, 済, ○ → True
- false, 0, no, いいえ, なし, × → False
- 曖昧な値 → エラー

### メール (email)
- 全角記号補正: ＠→@, ．→.
- 小文字化・前後空白除去

## 必須項目の二段階バリデーション

### ハード必須（エラー）
- email
- consent
- graduation_year または grade_label

### ソフト必須（警告）
- name（欠損時はメールアドレスのローカル部を使用）
- school_name
- interest_tags

## 文字コード対応
UTF-8 → CP932 → Shift-JIS → EUC-JP の順で自動検出

## 設計判断
1. **誤送信防止**: dev/staging環境では必ずMAIL_REDIRECT_TOにリダイレクト
2. **監査ログ**: すべての重要操作を記録（actor_role_snapshotで当時のロールを保持）
3. **認証**: MVP段階ではヘッダーベースの簡易認証（X-User-ID）
4. **二重送信防止**: send_logsテーブルでlead_id×scenario_id×scheduled_forの一意制約を想定（Step2で追加）
5. **卒業年度推定**: CSVにgraduation_yearがない場合、grade_labelから自動推定
6. **メールサービス疎結合**: Provider抽象化により将来の非同期化・プロバイダー切り替えに対応
7. **CSVインポート安全化**: プレビュー→確定の2ステップ、日本語列名対応、値の正規化

## 最近の変更
- 2024-12-22: CSVインポート事故率低減（正規化・プレビュー・ドライラン）
- 2024-12-22: graduation_year_source追加、EmailService抽象化
- 2024-12: Step1基盤実装完了
