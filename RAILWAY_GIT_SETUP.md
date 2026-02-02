# Railway × GitHub 連携ガイド

## ✅ 現在の状態

プロジェクトは既にGitリポジトリとして管理されており、GitHubの `origin/main` に接続されています。

---

## 🚀 RailwayとGitHubの連携方法

### 方法1: Railway Dashboardから連携（推奨）

#### 1. Railwayにログイン
1. [Railway Dashboard](https://railway.app) にアクセス
2. 既存のアカウントでログイン

#### 2. 新しいプロジェクトを作成
1. Dashboard → "New Project" をクリック
2. "Deploy from GitHub repo" を選択

#### 3. GitHubリポジトリを選択
1. GitHubアカウントを連携（初回のみ）
   - "Connect GitHub" をクリック
   - GitHubの認証画面で許可
2. リポジトリ一覧からこのプロジェクトを選択
3. "Deploy Now" をクリック

#### 4. 自動デプロイの設定
- Railwayは自動的に以下を検出します:
  - `railway.json` の設定
  - ビルドコマンド: `uv pip install -r pyproject.toml`
  - 起動コマンド: `uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT`

---

## 🔄 自動デプロイの仕組み

### 動作フロー

```
1. ローカルでコードを変更
   ↓
2. git add . && git commit -m "変更内容"
   ↓
3. git push origin main
   ↓
4. GitHubにプッシュ
   ↓
5. Railwayが自動的に検知
   ↓
6. 自動的にビルド開始
   ↓
7. デプロイ完了
```

### 自動デプロイの設定確認

1. Railway Dashboard → プロジェクト → "Settings"
2. "Source" タブで以下を確認:
   - ✅ GitHubリポジトリが連携されている
   - ✅ ブランチ: `main`（または指定したブランチ）
   - ✅ 自動デプロイ: 有効

---

## 📝 デプロイ前の準備

### 1. 変更をコミット・プッシュ

現在、未コミットの変更があります。まず、これらをコミットしてプッシュしてください:

```bash
# 変更をステージング
git add .

# コミット
git commit -m "パスワード認証とバルク操作機能を追加"

# GitHubにプッシュ
git push origin main
```

### 2. 重要なファイルを確認

以下のファイルがGitに含まれていることを確認:

- ✅ `railway.json` - Railway設定ファイル
- ✅ `pyproject.toml` - 依存関係
- ✅ `alembic/` - マイグレーションファイル
- ✅ `src/` - ソースコード

### 3. 除外すべきファイル

`.gitignore` で以下が除外されていることを確認:

- ❌ `.env` - 環境変数（Railwayで設定）
- ❌ `__pycache__/` - Pythonキャッシュ
- ❌ `*.pyc` - コンパイル済みファイル

---

## 🔧 Railwayでの設定

### 1. 環境変数の設定

Railway Dashboard → プロジェクト → "Variables" タブで設定:

```bash
APP_ENV=prod
DATABASE_URL=<PostgreSQLの接続情報>
SESSION_SECRET_KEY=<生成したシークレット>
UNSUBSCRIBE_SECRET=<生成したシークレット>
TRACKING_SECRET=<生成したシークレット>
BASE_URL=https://your-app-name.up.railway.app
SENDGRID_API_KEY=<SendGrid APIキー>
MAIL_FROM=noreply@your-domain.com
MAIL_REPLY_TO=support@your-domain.com
SCHEDULER_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
```

### 2. PostgreSQLデータベースの追加

1. プロジェクト → "New" → "Database" → "Add PostgreSQL"
2. データベースが作成されたら、"Variables" タブから `DATABASE_URL` をコピー
3. プロジェクトの "Variables" に `DATABASE_URL` を設定

---

## 🎯 ブランチ戦略（オプション）

### 本番環境とステージング環境を分ける場合

1. **mainブランチ** → 本番環境（自動デプロイ）
2. **developブランチ** → ステージング環境（手動デプロイ）

#### ステージング環境の設定

1. Railwayで別のプロジェクトを作成
2. "Settings" → "Source" で `develop` ブランチを指定
3. 環境変数で `APP_ENV=staging` を設定

---

## 🔍 デプロイの確認

### 1. デプロイログの確認

1. Railway Dashboard → プロジェクト → "Deployments"
2. 最新のデプロイをクリック
3. "View Logs" でログを確認

### 2. エラーが発生した場合

ログで以下を確認:

- ビルドエラー: 依存関係のインストールに失敗していないか
- 環境変数エラー: 必要な環境変数が設定されているか
- データベース接続エラー: `DATABASE_URL` が正しいか

---

## 🔄 継続的な運用

### コード変更の流れ

```bash
# 1. ローカルで開発
# コードを変更

# 2. 変更をコミット
git add .
git commit -m "機能追加: 〇〇"

# 3. GitHubにプッシュ
git push origin main

# 4. Railwayが自動的にデプロイ
# Dashboardで進行状況を確認
```

### 手動デプロイ（必要に応じて）

1. Railway Dashboard → "Deployments"
2. "Redeploy" をクリック

---

## 🛡️ セキュリティベストプラクティス

### 1. 環境変数の管理

- ✅ 機密情報はRailwayの "Variables" で管理
- ❌ `.env` ファイルをGitにコミットしない
- ✅ `.gitignore` で `.env` を除外

### 2. シークレットの生成

```bash
# ローカルで生成
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# RailwayのVariablesに設定
```

### 3. ブランチ保護（GitHub）

GitHubで `main` ブランチを保護する場合:

1. GitHubリポジトリ → "Settings" → "Branches"
2. "Add rule" で `main` ブランチを保護
3. "Require pull request reviews" を有効化（オプション）

---

## 📊 デプロイ履歴の確認

### Railway Dashboard

1. プロジェクト → "Deployments" タブ
2. 過去のデプロイ履歴を確認
3. 各デプロイのログを確認可能

### GitHub

1. GitHubリポジトリ → "Actions" タブ（GitHub Actions使用時）
2. コミット履歴で変更を確認

---

## 🔧 トラブルシューティング

### デプロイが自動的に開始されない

1. Railway Dashboard → "Settings" → "Source" を確認
2. GitHubリポジトリが正しく連携されているか確認
3. ブランチ名が正しいか確認（通常は `main`）

### ビルドが失敗する

1. "Deployments" → 最新のデプロイ → "View Logs" を確認
2. エラーメッセージを確認
3. よくある原因:
   - 依存関係のインストールエラー
   - 環境変数が不足
   - ビルドコマンドのエラー

### 環境変数が反映されない

1. Railway Dashboard → "Variables" を確認
2. 変数名が正しいか確認（大文字小文字を区別）
3. デプロイを再実行

---

## 💡 便利な機能

### 1. プレビューデプロイ

Pull Requestを作成すると、自動的にプレビュー環境が作成されます（Railway Proプラン）。

### 2. ロールバック

1. "Deployments" タブ
2. 過去のデプロイを選択
3. "Redeploy" をクリック

### 3. 環境変数の一括管理

- Railway Dashboard → "Variables" タブ
- 複数の環境変数を一度に設定・編集可能

---

## 📝 まとめ

✅ **GitHubと連携済み** - 既にGitリポジトリとして管理されている  
✅ **Railwayで自動デプロイ** - `git push` で自動的にデプロイ  
✅ **設定ファイル準備済み** - `railway.json` が作成済み  
✅ **簡単な運用** - コードをプッシュするだけでデプロイ完了  

---

## 🚀 次のステップ

1. ✅ 変更をコミット・プッシュ
2. ✅ Railwayでプロジェクトを作成
3. ✅ GitHubリポジトリを連携
4. ✅ 環境変数を設定
5. ✅ PostgreSQLを追加
6. ✅ マイグレーション実行
7. ✅ 動作確認
