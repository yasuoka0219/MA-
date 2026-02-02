# Railway デプロイ手順

## 🎯 Railwayを選ぶ理由（既に使用している場合）

✅ **管理が統一される** - 同じダッシュボードで複数プロジェクトを管理  
✅ **既に慣れている** - 学習コストが低い  
✅ **環境変数の管理が簡単** - 同じUIで設定  
✅ **コスト効率** - 複数プロジェクトでクレジットを共有可能  
✅ **デプロイフローが統一** - 同じワークフローで運用  

---

## 📋 前提条件

- Railwayアカウント（既に作成済み）
- GitHubリポジトリ（このプロジェクト）
- PostgreSQLデータベース（Railwayで作成）

---

## 🚀 デプロイ手順

### 1. 新しいプロジェクトを作成

1. [Railway Dashboard](https://railway.app) にログイン
2. "New Project" をクリック
3. "Deploy from GitHub repo" を選択
4. このプロジェクトのリポジトリを選択
5. "Deploy Now" をクリック

### 2. PostgreSQLデータベースを追加

1. プロジェクト内で "New" → "Database" → "Add PostgreSQL" をクリック
2. データベースが自動的に作成される
3. データベースをクリック → "Variables" タブ
4. `DATABASE_URL` の値をコピー（後で使用）

### 3. 環境変数の設定

プロジェクトの "Variables" タブで以下を設定:

#### 必須環境変数

```bash
# アプリケーション環境
APP_ENV=prod

# データベース接続（PostgreSQLのVariablesタブからコピー）
DATABASE_URL=postgresql://postgres:password@host:port/railway

# セッション管理（強力なランダム文字列）
SESSION_SECRET_KEY=<生成したシークレット>

# セキュリティシークレット（強力なランダム文字列）
UNSUBSCRIBE_SECRET=<生成したシークレット>
TRACKING_SECRET=<生成したシークレット>

# ベースURL（RailwayのデプロイURL）
BASE_URL=https://your-app-name.up.railway.app

# メール送信設定
SENDGRID_API_KEY=your-sendgrid-api-key
MAIL_FROM=noreply@your-domain.com
MAIL_REPLY_TO=support@your-domain.com

# スケジューラー設定
SCHEDULER_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
```

#### オプション環境変数（LINEを使用する場合）

```bash
LINE_CHANNEL_ACCESS_TOKEN=your-line-channel-access-token
LINE_CHANNEL_SECRET=your-line-channel-secret
LINE_FRIEND_ADD_URL=https://line.me/R/ti/p/@your-line-id
```

### 4. シークレットの生成

ローカルで以下のコマンドを実行してシークレットを生成:

```bash
# 方法1: Pythonで生成
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 方法2: スクリプトを使用
./scripts/generate-secrets.sh
```

生成した値を `SESSION_SECRET_KEY`、`UNSUBSCRIBE_SECRET`、`TRACKING_SECRET` に設定してください。

### 5. ビルド設定の確認

Railwayは自動的に `railway.json` を検出しますが、手動で設定する場合:

1. プロジェクト → "Settings" → "Build & Deploy"
2. Build Command: `uv pip install -r pyproject.toml`
3. Start Command: `uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT`

### 6. デプロイの確認

1. Railwayが自動的にデプロイを開始します
2. "Deployments" タブで進行状況を確認
3. ログを確認してエラーがないかチェック

### 7. データベースマイグレーションの実行

デプロイが完了したら、Railway CLIを使用してマイグレーションを実行:

#### Railway CLIのインストール（未インストールの場合）

```bash
# macOS
brew install railway

# または npm経由
npm i -g @railway/cli
```

#### マイグレーション実行

```bash
# Railwayにログイン
railway login

# プロジェクトをリンク
railway link

# マイグレーション実行
railway run uv run alembic upgrade head
```

または、Railway Dashboardの "Deployments" → "View Logs" で確認しながら、以下のコマンドを実行:

```bash
railway run bash
# シェル内で
uv run alembic upgrade head
```

### 8. 初期ユーザーの作成

同じRailway CLIで:

```bash
railway run uv run python -m src.ma_tool.seed
```

または、既存のユーザーにパスワードを設定する場合:

```bash
railway run python -c "
from src.ma_tool.database import SessionLocal
from src.ma_tool.models.user import User
from src.ma_tool.services.password import hash_password
from sqlalchemy import select

db = SessionLocal()
try:
    users = db.execute(select(User)).scalars().all()
    default_password = 'password123'
    
    for user in users:
        if not user.password_hash:
            user.password_hash = hash_password(default_password)
            print(f'ユーザー {user.email} に初期パスワードを設定しました')
    
    db.commit()
    print('完了')
finally:
    db.close()
"
```

### 9. カスタムドメインの設定（オプション）

1. プロジェクト → "Settings" → "Domains"
2. "Custom Domain" を追加
3. DNS設定を追加（Railwayが指示を表示）

---

## 🔧 Railway固有の設定

### 環境変数の参照

PostgreSQLの接続情報を自動的に参照する場合:

1. プロジェクト → "Variables" タブ
2. "New Variable" をクリック
3. Name: `DATABASE_URL`
4. Value: PostgreSQLサービスの "Variables" タブから `DATABASE_URL` をコピー
   - または、PostgreSQLサービスを選択 → "Connect" → "Private Networking" の接続文字列を使用

### リソース設定

1. プロジェクト → "Settings" → "Resources"
2. CPU/メモリを調整（必要に応じて）
3. デフォルトで十分な場合が多い

### ログの確認

1. プロジェクト → "Deployments" タブ
2. 最新のデプロイをクリック
3. "View Logs" でリアルタイムログを確認

---

## 🔄 継続的な運用

### 自動デプロイ

- GitHubにプッシュすると自動的にデプロイされます
- 環境変数の変更も即座に反映されます

### 手動デプロイ

1. プロジェクト → "Deployments" タブ
2. "Redeploy" をクリック

### ロールバック

1. プロジェクト → "Deployments" タブ
2. 過去のデプロイを選択
3. "Redeploy" をクリック

---

## 📊 コスト管理

### 無料クレジット

- Railwayは月$5の無料クレジットを提供
- 複数のプロジェクトで共有可能
- 使用量は Dashboard → "Usage" で確認

### コスト最適化のヒント

1. **スリープ設定**: 使用しない時間は自動的にスリープ（無料プラン）
2. **リソース調整**: 必要最小限のリソースに設定
3. **データベース**: PostgreSQLは使用量に応じて課金

---

## 🐛 トラブルシューティング

### デプロイが失敗する

1. "Deployments" タブでログを確認
2. エラーメッセージを確認
3. よくある原因:
   - 環境変数が不足している
   - ビルドコマンドが失敗している
   - 依存関係のインストールに失敗

### データベース接続エラー

1. PostgreSQLサービスの "Variables" タブで接続情報を確認
2. `DATABASE_URL` が正しく設定されているか確認
3. プライベートネットワークを使用しているか確認

### マイグレーションエラー

```bash
# 現在のマイグレーション状態を確認
railway run uv run alembic current

# マイグレーション履歴を確認
railway run uv run alembic history

# 特定のバージョンにロールバック（必要に応じて）
railway run uv run alembic downgrade <revision>
```

---

## 🔐 セキュリティチェックリスト

デプロイ前に確認:

- [ ] `APP_ENV=prod` が設定されている
- [ ] `SESSION_SECRET_KEY` が強力なランダム文字列に設定されている
- [ ] `UNSUBSCRIBE_SECRET` が `change-me-in-production` から変更されている
- [ ] `TRACKING_SECRET` が `change-me-in-production` から変更されている
- [ ] `DATABASE_URL` が正しく設定されている
- [ ] `BASE_URL` が正しいRailway URLに設定されている
- [ ] `SENDGRID_API_KEY` が設定されている
- [ ] `MAIL_FROM` が正しいドメインに設定されている

---

## 📝 次のステップ

1. ✅ デプロイ完了
2. ✅ マイグレーション実行
3. ✅ 初期ユーザー作成
4. 🔄 動作確認
5. 🔄 カスタムドメイン設定（オプション）
6. 🔄 モニタリング設定（オプション）

---

## 💡 既存プロジェクトとの統合

### 同じRailwayアカウントで管理

- Dashboardで複数のプロジェクトを切り替え可能
- 環境変数はプロジェクトごとに管理
- クレジットは共有される

### ベストプラクティス

1. **プロジェクト名を明確に**: `ma-tool-prod` など
2. **環境変数を整理**: プロジェクトごとに明確に分離
3. **ログを定期的に確認**: 問題の早期発見

---

## 📚 参考リンク

- [Railway Documentation](https://docs.railway.app/)
- [Railway CLI Documentation](https://docs.railway.app/develop/cli)
- [PostgreSQL on Railway](https://docs.railway.app/databases/postgresql)
