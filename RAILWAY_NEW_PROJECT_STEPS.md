# Railway：MA- 用に新規プロジェクトを作成する手順

既存アプリとは別の **New Project** で MA- だけを管理する手順です。

---

## 1. 新規プロジェクトを作成

1. [Railway Dashboard](https://railway.app) にログイン
2. **「New Project」** をクリック
3. **「Deploy from GitHub repo」** を選択
4. リポジトリ一覧から **MA-** のリポジトリを選択  
   （表示されない場合は「Configure GitHub App」でリポジトリへのアクセスを許可）
5. デプロイが自動で開始される（この時点では環境変数未設定のため失敗しても問題ありません）

---

## 2. PostgreSQL を追加

1. 作成されたプロジェクトの画面で **「+ New」** をクリック
2. **「Database」** → **「Add PostgreSQL」** を選択
3. PostgreSQL サービスが追加されたら、そのサービス（カード）をクリック
4. **「Variables」** タブを開く
5. **`DATABASE_URL`** の値（接続文字列）をコピーしてメモ  
   → 次のステップでアプリの環境変数に貼り付けます

---

## 3. アプリの環境変数を設定

1. プロジェクト内の **Web サービス**（MA- のアプリの方）のカードをクリック
2. **「Variables」** タブを開く
3. **「+ New Variable」** または **「Raw Editor」** で、以下の変数を追加

### 必須

| 変数名 | 値 |
|--------|-----|
| `DATABASE_URL` | ステップ2でコピーした PostgreSQL の接続文字列 |
| `APP_ENV` | `prod` |
| `SESSION_SECRET_KEY` | 下記「シークレット生成」で作成した値の1つ目 |
| `UNSUBSCRIBE_SECRET` | 同上の2つ目 |
| `TRACKING_SECRET` | 同上の3つ目 |

### シークレットの生成（ローカルで実行）

ターミナルで以下を **3回** 実行し、出た値をそれぞれ上記3つに設定してください。

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### BASE_URL（デプロイ後に設定）

1. いったん保存せずに進んでOKです
2. ステップ5でドメインを発行したあと、**「Variables」** に次を追加  
   - 変数名: `BASE_URL`  
   - 値: `https://（発行したドメイン）.up.railway.app`

### オプション（必要に応じて後から追加）

- `SENDGRID_API_KEY` / `MAIL_FROM` / `MAIL_REPLY_TO` … メール送信する場合
- `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET` / `LINE_FRIEND_ADD_URL` … LINE 連携する場合

---

## 4. デプロイの実行

1. **「Deployments」** タブを開く
2. 最新のデプロイが自動で走っていなければ **「Redeploy」** または **「Deploy」** をクリック
3. ビルド・デプロイが成功するまでログで確認（エラーが出たら Variables の typo や不足を確認）

---

## 5. 公開 URL（ドメイン）を発行

1. Web サービス（MA- アプリ）の **「Settings」** を開く
2. **「Networking」** の **「Generate Domain」** をクリック
3. 表示された URL（例: `ma-tool-production.up.railway.app`）が本番のアクセス先になります
4. **「Variables」** に `BASE_URL` を追加  
   - 値: `https://（表示されたドメイン）`  
   （例: `https://ma-tool-production.up.railway.app`）
5. 必要なら **「Redeploy」** で再デプロイ（Variables の変更は多くの場合そのまま反映されます）

---

## 6. マイグレーションと初期ユーザー（初回のみ）

1. ターミナルで [Railway CLI](https://docs.railway.app/develop/cli) をインストール（未導入の場合）  
   ```bash
   brew install railway   # macOS
   ```
2. ログインとプロジェクト紐づけ  
   ```bash
   railway login
   railway link   # 表示される一覧から「MA- 用に作ったプロジェクト」を選択
   ```
3. マイグレーション実行  
   ```bash
   railway run uv run alembic upgrade head
   ```
4. 初期ログインユーザーを作成（必要なら）  
   ```bash
   railway run uv run python -m src.ma_tool.seed
   ```
5. 発行した URL にブラウザでアクセスし、ログインできるか確認

---

## 7. 今後の運用（修正をすぐ本番に反映）

- **main** ブランチに push すると、このプロジェクトだけが自動で再デプロイされます
- 既存アプリのプロジェクトには影響しません
- マイグレーションを毎回の起動時に実行したい場合は、Web サービスの **Settings** → **Deploy** で Start Command を  
  **`sh scripts/start.sh`**  
  に変更してください

---

## チェックリスト

- [ ] New Project で MA- 用プロジェクトを作成した
- [ ] 同じプロジェクト内に PostgreSQL を追加した
- [ ] Web サービスの Variables に必須5項目を設定した
- [ ] Generate Domain で URL を発行し、`BASE_URL` を設定した
- [ ] `railway run uv run alembic upgrade head` を実行した
- [ ] 必要なら seed で初期ユーザーを作成した
- [ ] ブラウザで本番 URL にアクセスして動作確認した

ここまで完了すれば、MA- は既存アプリと分けた「MA- 専用プロジェクト」として運用できます。
