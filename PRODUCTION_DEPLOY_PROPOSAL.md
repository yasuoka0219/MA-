# 本番環境デプロイ・運用の提案

## ご希望の整理

1. **いま本番環境にアップしたい**
2. **修正した内容をすぐ本番に反映したい**（push → 自動デプロイ）
3. **ドメインは後から接続する**（まずは提供URLで運用）

---

## 推奨: Railway で本番運用

このリポジトリにはすでに **Railway** 用の設定（`railway.json`）と手順（`RAILWAY_DEPLOY.md`）があるため、**Railway を本番環境**として使うのがいちばんスムーズです。

| 項目 | 内容 |
|------|------|
| 自動デプロイ | GitHub の **main** に push するたびに自動ビルド・デプロイ |
| ドメイン | 最初は `xxxx.up.railway.app`。後から Settings → Domains で独自ドメインを追加可能 |
| DB | 同じプロジェクト内で PostgreSQL を追加するだけ |
| コスト | 月 $5 分の無料クレジット。超過分は従量課金 |

---

## 運用フロー（修正 → 本番反映）

```
ローカルで修正
    ↓
git add / git commit
    ↓
git push origin main
    ↓
Railway が検知して自動ビルド・デプロイ
    ↓
数分で本番に反映
```

**やること**: 普段どおり `main` に push するだけです。特別な CI 設定は不要です。

---

## 実施手順（初回のみ）

### 1. Railway でプロジェクト作成

1. [Railway](https://railway.app) にログイン（GitHub 連携可）
2. **New Project** → **Deploy from GitHub repo**
3. リポジトリ `yasuoka0219/MA-`（またはご利用のリポジトリ）を選択
4. デプロイ用のブランチを **main** に設定（デフォルトのまま）

### 2. PostgreSQL を追加

1. 同じプロジェクト内で **New** → **Database** → **Add PostgreSQL**
2. 作成された DB をクリック → **Variables** タブで **DATABASE_URL** をコピー

### 3. 環境変数を設定

アプリのサービス（Web サービス）の **Variables** で以下を設定します。

**必須**

| 変数名 | 例・備考 |
|--------|----------|
| `DATABASE_URL` | PostgreSQL の Variables からコピーした値 |
| `APP_ENV` | `prod` |
| `SESSION_SECRET_KEY` | 下記コマンドで生成したランダム文字列 |
| `UNSUBSCRIBE_SECRET` | 同様に生成 |
| `TRACKING_SECRET` | 同様に生成 |
| `BASE_URL` | いったん `https://<サービス名>.up.railway.app`（後でドメイン変更可） |

**シークレット生成（ローカルで実行）**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

上記を 3 回実行し、それぞれ `SESSION_SECRET_KEY` / `UNSUBSCRIBE_SECRET` / `TRACKING_SECRET` に設定してください。

**本番で推奨（あとからでも可）**

- `SENDGRID_API_KEY` / `MAIL_FROM` / `MAIL_REPLY_TO` … メール送信する場合
- `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET` … LINE 連携する場合

### 4. 初回デプロイ後: マイグレーションと初期ユーザー

デプロイが成功したら、**一度だけ** 以下を実行します（Railway CLI 使用）。

```bash
# CLI 未導入の場合
brew install railway   # macOS

railway login
railway link          # 対象プロジェクトを選択

# マイグレーション
railway run uv run alembic upgrade head

# 初期ログインユーザー（必要なら）
railway run uv run python -m src.ma_tool.seed
```

2 回目以降のデプロイでは、**起動時にマイグレーションを実行する**設定（後述）にしておけば、push するだけでスキーマも含めて本番に反映されます。

### 5. 公開 URL の確認

- Railway のサービス画面で **Settings** → **Networking** → **Generate Domain** を実行すると `xxxx.up.railway.app` が発行されます。
- その URL を `BASE_URL` に設定し直し、必要なら再デプロイ（または Variables の更新だけ）。

---

## ドメインを後から接続するとき

1. Railway のサービス → **Settings** → **Domains**
2. **Custom Domain** を追加し、表示された **CNAME**（または A レコード）を DNS に設定
3. 証明書は Railway が自動発行
4. 発行されたドメインで問題なければ、**環境変数 `BASE_URL`** をそのドメインに変更（例: `https://ma.example.com`）

メールのリンクやトラッキングは `BASE_URL` を参照するため、ドメイン変更後は必ず `BASE_URL` を更新してください。

---

## 修正をすぐ本番に反映するためのポイント

1. **デプロイブランチを main に統一**  
   Railway の「Deploy from GitHub」で、**Branch** を **main** にしておく。

2. **作業の流れ**  
   - 機能追加・修正はブランチで実施  
   - レビューやテスト後、`main` にマージ（または push）  
   - マージ／push がトリガーで自動デプロイ

3. **マイグレーションを自動実行する（推奨）**  
   新しいマイグレーションを追加したとき、毎回 `railway run alembic upgrade head` を手で打つと手間なので、**起動前にマイグレーションを実行する起動スクリプト**を使うと安全です。  
   リポジトリに `scripts/start.sh` を追加し、Railway の Start Command をそれに差し替える案を以下に示します。

---

## 起動コマンドでマイグレーションを通す（任意）

デプロイのたびに「マイグレーションを忘れずに実行」したい場合は、Start Command を次のように変更します。

**現在（railway.json）**

```text
uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT
```

**変更案**

- Start Command を次に変更:  
  `sh scripts/start.sh`  
- または Railway の **Variables** で **Start Command** を上書き:  
  `uv run alembic upgrade head && uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT`

これで、毎回のデプロイ時に自動で `alembic upgrade head` が走り、新しいマイグレーションがあれば適用されます。

---

## 代替: Render を使う場合

- [Render](https://render.com) にアカウント作成 → GitHub 連携
- リポジトリの **render.yaml** をそのまま使うか、Dashboard で **Web Service** と **PostgreSQL** を追加
- **Build Command**: `uv pip install -r pyproject.toml`
- **Start Command**: `uvicorn src.ma_tool.main:app --host 0.0.0.0 --port $PORT`
- 環境変数は Dashboard で設定（Railway と同様の項目）
- **main への push で自動デプロイ**、**後から Custom Domain を追加**可能です。

---

## まとめ

| やりたいこと | 方法 |
|--------------|------|
| 本番環境にアップする | Railway（または Render）で「GitHub からデプロイ」＋ PostgreSQL 追加 ＋ 環境変数設定 |
| 修正をすぐ本番に反映 | **main に push** するだけ（自動デプロイ） |
| ドメインは後から | Railway/Render の **Settings → Domains** でカスタムドメインを追加し、`BASE_URL` を更新 |

まずは **Railway で main に push → 自動デプロイ** までを確立し、その後で独自ドメイン接続と機能追加に進む流れをおすすめします。
