# MA Tool - 大学向けマーケティングオートメーションツール

## 概要
大学が保有する高校生/学生データ（CSV）に対して、卒業年度×イベント起点で、学年最適化したメールを自動配信するMAツールのMVP版。

## 現在の状態
- **Step1基盤** 完了
- **Step2シナリオ実行エンジン** 完了
- **Step3テンプレート管理・承認フロー** 完了
- FastAPI + PostgreSQL + SQLAlchemy 2.x + Alembic + APScheduler + Jinja2
- 個人情報保護対応（同意・配信停止・監査ログ・権限）
- メール誤送信防止（dev/staging環境でのリダイレクト制御）
- **追加機能**: 学年（grade_label）からの卒業年度推定
- **追加機能**: EmailService抽象化（非同期対応準備）
- **追加機能**: CSVインポート事故率低減（正規化・プレビュー・ドライラン）
- **追加機能**: シナリオ自動実行（5分間隔、レート制限、リトライ）
- **追加機能**: メール開封トラッキング（透過1x1 GIF）
- **追加機能**: テンプレート承認ワークフロー（draft→pending→approved/rejected）

## プロジェクト構造
```
src/ma_tool/
├── main.py           # FastAPIアプリケーション
├── config.py         # 環境変数管理（Pydantic Settings）
├── database.py       # DBセッション管理
├── seed.py           # 初期データ投入
├── seed_step2.py     # Step2テストデータ（100リード、3テンプレート、3シナリオ、50イベント）
├── api/
│   ├── deps.py       # 認証・依存性注入
│   └── endpoints/
│       ├── health.py      # ヘルスチェック
│       ├── csv_import.py  # CSVインポート（プレビュー対応）
│       ├── unsubscribe.py   # 配信停止
│       ├── scheduler_api.py # スケジューラー監視API
│       ├── tracking.py      # 開封トラッキング（1x1 GIF）
│       ├── templates.py     # テンプレートREST API
│       └── views.py         # テンプレート管理UI（Jinja2）
├── templates/         # Jinja2テンプレート
│   ├── base.html           # ベースレイアウト
│   ├── template_list.html  # テンプレート一覧
│   ├── template_form.html  # 作成・編集フォーム
│   └── template_detail.html # 詳細・承認画面
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
    ├── unsubscribe.py     # 配信停止サービス
    ├── scenario_engine.py  # シナリオ評価ロジック
    ├── scheduler.py        # APSchedulerラッパー・送信処理
    └── template.py         # テンプレート管理サービス
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
| TRACKING_SECRET | - | 開封計測用 |
| RATE_LIMIT_PER_MINUTE | - | メール送信レート制限（デフォルト: 60） |

## APIエンドポイント
- `GET /` - API情報
- `GET /health` - ヘルスチェック
- `POST /import/preview` - CSVプレビュー（ドライラン）
- `POST /import/confirm` - CSVインポート確定
- `POST /import/csv` - CSVインポート（レガシー互換）
- `GET /import/errors/{session_id}` - エラーCSVダウンロード
- `GET /unsubscribe/{token}` - 配信停止
- `GET /scheduler/status` - スケジューラー状態
- `GET /scheduler/pending` - 送信待ちメール一覧
- `POST /scheduler/trigger` - 手動トリガー（テスト用）
- `GET /track/{token}/open.gif` - 開封トラッキングピクセル
- **テンプレート管理API**:
  - `GET /api/templates` - テンプレート一覧
  - `POST /api/templates` - テンプレート作成
  - `GET /api/templates/{id}` - テンプレート詳細
  - `PUT /api/templates/{id}` - テンプレート更新
  - `POST /api/templates/{id}/submit` - 承認申請
  - `POST /api/templates/{id}/approve` - 承認
  - `POST /api/templates/{id}/reject` - 差戻し
  - `POST /api/templates/{id}/clone` - 複製
  - `GET /api/templates/variables` - 利用可能な変数一覧
- **テンプレート管理UI**:
  - `GET /templates` - テンプレート一覧画面
  - `GET /templates/new` - 新規作成画面
  - `GET /templates/{id}` - 詳細画面
  - `GET /templates/{id}/edit` - 編集画面

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
8. **シナリオ実行**: 5分間隔でスケジューラーが新規イベントを処理し、配信条件を満たすリードにメール予約を作成
9. **重複送信防止**: send_logsテーブルにlead_id×scenario_id×event_idの一意制約、個別コミットで堅牢性確保
10. **送信時間帯制限**: 9:00-20:00 JST（時間外は翌9:00にロールオーバー）
11. **レート制限**: 1分あたり最大60通（設定可能）、上限到達時は次回tickで継続
12. **テンプレート承認フロー**: draft→pending→approved/rejected、承認済みは編集不可（複製して新版作成）
13. **ロールベースアクセス制御**: admin（全権限）、editor（作成・編集・申請）、approver（承認・差戻し）、viewer（閲覧のみ）

## シナリオ配信条件

メールが配信されるには以下のすべてを満たす必要があります:

1. **同意確認**: lead.consent = True
2. **配信停止確認**: lead.unsubscribed = False
3. **テンプレート承認**: template.approved = True
4. **卒業年度ルール**: scenarioのgraduation_year_ruleに合致
   - `{"type": "all"}` - 全リード対象
   - `{"type": "in", "years": [2026, 2027]}` - 特定年度リスト
   - `{"type": "within_months", "months": 18}` - 卒業まで18ヶ月以内（学年度考慮）
5. **頻度制限**: 同一シナリオの最終送信からfrequency_days日以上経過
6. **重複防止**: 同一lead×scenario×eventの組み合わせで未送信

## graduation_year_rule「within_months」の計算

学年度（4月〜翌3月）を考慮して計算:
- 現在の学年度 = 現在月≧4なら現在年+1、そうでなければ現在年
- N ヶ月後の学年度 = (現在日 + Nヶ月)の月≧4ならその年+1
- 対象 = 卒業年度が現在学年度〜N ヶ月後学年度の範囲内

## ロール権限マトリックス

| 操作 | admin | editor | approver | viewer |
|------|-------|--------|----------|--------|
| テンプレート閲覧 | ○ | ○ | ○ | ○ |
| テンプレート作成 | ○ | ○ | × | × |
| テンプレート編集 | ○ | ○ | × | × |
| 承認申請 | ○ | ○ | × | × |
| 承認/差戻し | ○ | × | ○ | × |
| テンプレート複製 | ○ | ○ | × | × |
| テンプレート削除 | ○ | × | × | × |

## テンプレートステータス遷移

```
draft ─────→ pending ─────→ approved
  ↑             │
  │             ↓
  └───────── rejected
```

- **draft**: 作成直後、編集中
- **pending**: 承認待ち（editorが申請）
- **approved**: 承認済み（メール送信可能、編集不可）
- **rejected**: 差戻し（理由付き、編集して再申請可能）

## 動作確認手順

### 1. シードデータ投入
```bash
python -m src.ma_tool.seed
```

テストユーザーが作成されます:
- ID 1: admin@example.com (admin)
- ID 2: editor@example.com (editor)
- ID 3: approver@example.com (approver)
- ID 4: viewer@example.com (viewer)

### 2. ブラウザでアクセス
`http://localhost:5000/templates`

### 3. 承認フローテスト

1. **Editorでログイン**: 画面右上のドロップダウンで「Editor User」を選択
2. **テンプレート作成**: 「New Template」から新規作成
3. **承認申請**: 作成したテンプレートの詳細画面で「Submit for Approval」
4. **Approverでログイン**: ドロップダウンで「Approver User」に切り替え
5. **承認**: 該当テンプレートを開き「Approve」または「Reject」

## 最近の変更
- 2024-12-22: Step3テンプレート管理・承認フロー実装完了
- 2024-12-22: Step2シナリオ実行エンジン実装完了
- 2024-12-22: CSVインポート事故率低減（正規化・プレビュー・ドライラン）
- 2024-12-22: graduation_year_source追加、EmailService抽象化
- 2024-12: Step1基盤実装完了
