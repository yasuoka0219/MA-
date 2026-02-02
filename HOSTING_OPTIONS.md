# 本番環境ホスティング選択肢

## 🎯 推奨順（スモールスタート向け）

### 1. **Render** ⭐ 最も推奨（スモールスタート）

**特徴:**
- ✅ 無料プランあり（制限あり）
- ✅ PostgreSQLが統合されている
- ✅ GitHub連携で自動デプロイ
- ✅ SSL証明書が自動設定
- ✅ 環境変数の管理が簡単
- ✅ ログの確認が簡単

**料金:**
- Webサービス: 無料（スリープあり） / $7/月（常時起動）
- PostgreSQL: 無料（90日） / $7/月（永続）

**デプロイ手順:**
1. [Render](https://render.com) にアカウント作成
2. GitHubリポジトリを連携
3. "New Web Service" を選択
4. 環境変数を設定
5. Build Command: `uv pip install -r pyproject.toml`
6. Start Command: `uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT`
7. PostgreSQLデータベースを追加

**メリット:**
- セットアップが最も簡単
- 管理が不要（インフラ管理不要）
- スケーリングが容易

**デメリット:**
- 無料プランはスリープする（初回アクセスが遅い）
- カスタマイズ性が低い

---

### 2. **Railway** ⭐ 推奨

**特徴:**
- ✅ 無料プランあり（$5クレジット/月）
- ✅ PostgreSQLが統合されている
- ✅ GitHub連携で自動デプロイ
- ✅ SSL証明書が自動設定
- ✅ 環境変数の管理が簡単

**料金:**
- Webサービス: $5クレジット/月（無料）
- PostgreSQL: $5クレジット/月に含まれる

**デプロイ手順:**
1. [Railway](https://railway.app) にアカウント作成
2. "New Project" → "Deploy from GitHub"
3. リポジトリを選択
4. PostgreSQLを追加
5. 環境変数を設定
6. 自動デプロイ

**メリット:**
- Renderと同様に簡単
- 無料クレジットが使いやすい
- ログが分かりやすい

**デメリット:**
- 無料クレジットを使い切ると課金
- カスタマイズ性が低い

---

### 3. **Fly.io** ⭐ 推奨（グローバル展開向け）

**特徴:**
- ✅ 無料プランあり（3つのVM）
- ✅ グローバルCDN
- ✅ PostgreSQLが統合されている
- ✅ Dockerベース
- ✅ スケーリングが容易

**料金:**
- Webサービス: 無料（3VMまで）
- PostgreSQL: $1.94/月（最小プラン）

**デプロイ手順:**
1. [Fly.io](https://fly.io) にアカウント作成
2. `flyctl` CLIをインストール
3. `fly launch` でデプロイ
4. PostgreSQLを追加: `fly postgres create`

**メリット:**
- グローバル展開が容易
- パフォーマンスが良い
- 無料プランが充実

**デメリット:**
- CLI操作が必要
- 設定がやや複雑

---

### 4. **DigitalOcean App Platform** 

**特徴:**
- ✅ マネージドサービス
- ✅ PostgreSQLが統合されている
- ✅ GitHub連携
- ✅ SSL証明書が自動設定

**料金:**
- Webサービス: $5/月（Basic）
- PostgreSQL: $15/月（最小プラン）

**デメリット:**
- 無料プランがない
- コストがやや高い

---

### 5. **VPS（Vultr / DigitalOcean Droplets / Linode）**

**特徴:**
- ✅ 完全なコントロール
- ✅ カスタマイズ性が高い
- ✅ コストが安い（小規模の場合）

**料金:**
- VPS: $6-12/月（最小プラン）
- PostgreSQL: 自分で構築（VPS内）

**デプロイ手順:**
- `DEPLOYMENT.md` の手順に従う
- Nginx、systemd、PostgreSQLを自分で設定

**メリット:**
- 完全なコントロール
- 学習になる
- カスタマイズ性が高い

**デメリット:**
- セットアップが複雑
- インフラ管理が必要
- セキュリティパッチの適用が必要

---

### 6. **AWS / Google Cloud Platform / Azure**

**特徴:**
- ✅ エンタープライズ向け
- ✅ スケーラビリティが高い
- ✅ 豊富なサービス

**料金:**
- 従量課金（使用量に応じて）
- 小規模なら月$20-50程度

**デメリット:**
- 設定が複雑
- コスト管理が難しい
- スモールスタートには過剰

---

## 🎯 推奨：スモールスタートの場合

### **Render または Railway を推奨**

**理由:**
1. **セットアップが簡単** - インフラ管理不要
2. **無料プランがある** - 初期コストが低い
3. **PostgreSQLが統合** - 別途データベースサーバー不要
4. **自動デプロイ** - GitHub連携で簡単
5. **SSL証明書自動** - HTTPS設定が不要

---

## 📊 比較表

| サービス | 無料プラン | 最小月額 | セットアップ | PostgreSQL | 推奨度 |
|---------|-----------|---------|------------|-----------|--------|
| **Render** | ✅ | $7 | ⭐⭐⭐⭐⭐ | ✅統合 | ⭐⭐⭐⭐⭐ |
| **Railway** | ✅ | $0-5 | ⭐⭐⭐⭐⭐ | ✅統合 | ⭐⭐⭐⭐⭐ |
| **Fly.io** | ✅ | $1.94 | ⭐⭐⭐ | ✅統合 | ⭐⭐⭐⭐ |
| **DigitalOcean App** | ❌ | $20 | ⭐⭐⭐⭐ | ✅統合 | ⭐⭐⭐ |
| **VPS** | ❌ | $6-12 | ⭐⭐ | ❌自分で構築 | ⭐⭐ |
| **AWS/GCP/Azure** | ❌ | $20-50 | ⭐ | ❌自分で構築 | ⭐ |

---

## 🚀 具体的なデプロイ手順（Render推奨）

### 1. Renderアカウント作成
- https://render.com にアクセス
- GitHubアカウントでサインアップ

### 2. PostgreSQLデータベース作成
1. Dashboard → "New +" → "PostgreSQL"
2. データベース名を設定
3. リージョンを選択（Tokyo推奨）
4. プランを選択（FreeまたはStarter）
5. "Create Database" をクリック
6. 接続情報（Internal Database URL）をコピー

### 3. Webサービス作成
1. Dashboard → "New +" → "Web Service"
2. GitHubリポジトリを連携
3. 設定:
   - **Name**: ma-tool
   - **Environment**: Python 3
   - **Build Command**: `uv pip install -r pyproject.toml`
   - **Start Command**: `uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free（またはStarter）

### 4. 環境変数の設定
RenderのDashboard → 作成したWebサービス → "Environment" タブで以下を設定:

```bash
APP_ENV=prod
DATABASE_URL=<PostgreSQLのInternal Database URL>
SESSION_SECRET_KEY=<生成したシークレット>
UNSUBSCRIBE_SECRET=<生成したシークレット>
TRACKING_SECRET=<生成したシークレット>
BASE_URL=https://your-app.onrender.com
SENDGRID_API_KEY=<SendGrid APIキー>
MAIL_FROM=noreply@your-domain.com
MAIL_REPLY_TO=support@your-domain.com
SCHEDULER_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
```

### 5. マイグレーション実行
RenderのDashboard → 作成したWebサービス → "Shell" タブで:

```bash
uv run alembic upgrade head
```

### 6. 初期ユーザー作成
同じShellで:

```bash
uv run python -m src.ma_tool.seed
```

### 7. デプロイ完了
- 自動的にデプロイが開始される
- 完了後、`https://your-app.onrender.com` でアクセス可能

---

## 🔄 継続的な運用

### 自動デプロイ
- GitHubにプッシュすると自動デプロイ
- 環境変数の変更も即座に反映

### ログの確認
- Render Dashboard → "Logs" タブで確認
- リアルタイムでログを確認可能

### バックアップ
- PostgreSQLのバックアップは自動（有料プラン）
- 無料プランは手動バックアップ推奨

---

## 💡 その他の推奨事項

### ドメイン設定（オプション）
1. 独自ドメインを取得
2. Render Dashboard → "Custom Domains" で設定
3. DNS設定を追加

### モニタリング
- Renderのダッシュボードで基本的な監視が可能
- より詳細な監視が必要な場合は、Sentryなどを追加

### スケーリング
- トラフィックが増えたらプランをアップグレード
- Renderは自動スケーリングに対応

---

## 📝 まとめ

**スモールスタートなら:**
1. **Render** または **Railway** を選択
2. 無料プランから開始
3. 成長に応じてプランをアップグレード

**理由:**
- セットアップが最も簡単
- インフラ管理が不要
- コストが低い
- スケーリングが容易
