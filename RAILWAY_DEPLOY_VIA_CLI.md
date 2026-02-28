# Railway：リポジトリが一覧に出ない場合のデプロイ方法（CLI でデプロイ）

GitHub のリポジトリ一覧に MA- が表示されない場合は、**空のプロジェクトを作成してから、Railway CLI でローカルのコードをデプロイ**する方法で進められます。

---

## 前提

- MA- のコードがローカル（または GitHub から clone したフォルダ）にあること
- ターミナルでコマンドを実行できること

---

## 手順

### 1. 空のプロジェクトを Railway で作成

1. [Railway Dashboard](https://railway.app) にログイン
2. **「New Project」** をクリック
3. **「Empty Project」**（空のプロジェクト）を選択  
   ※「Deploy from GitHub repo」は使わず、空プロジェクトで作成します
4. プロジェクト名を分かりやすくしておく（例: `ma-tool`）

---

### 2. PostgreSQL を追加

1. 作成されたプロジェクト画面で **「+ New」** をクリック
2. **「Database」** → **「Add PostgreSQL」** を選択
3. PostgreSQL のサービス（カード）をクリック → **「Variables」** タブ
4. **`DATABASE_URL`** の値をコピーしてメモ（あとで使います）

---

### 3. Railway CLI のインストールとログイン

ローカルのターミナルで実行します。

```bash
# macOS
brew install railway

# ログイン（ブラウザが開きます）
railway login
```

---

### 4. MA- のフォルダでプロジェクトに紐づける

MA- のリポジトリがあるディレクトリに移動して、さきほど作った「空のプロジェクト」に紐づけます。

```bash
cd /Users/okazakikatsuhiro/MA-   # MA- のフォルダへ

# 紐づけ（一覧から「空で作った MA- 用プロジェクト」を選択）
railway link
```

`railway link` で表示される一覧から、**手順1で作ったプロジェクト**を選んでください。

---

### 5. 環境変数を Railway で設定

CLI からでも設定できますが、**Dashboard で設定する方が分かりやすい**です。

1. Railway Dashboard で、MA- 用プロジェクトを開く
2. **「+ New」** → **「Empty Service」** または、既にサービスが 1 つあればその **Web サービス**をクリック  
   （空プロジェクトの場合は、次に「デプロイ」するとサービスが自動でできます）
3. そのサービスの **「Variables」** タブで、以下を追加

| 変数名 | 値 |
|--------|-----|
| `DATABASE_URL` | 手順2でコピーした PostgreSQL の接続文字列 |
| `APP_ENV` | `prod` |
| `SESSION_SECRET_KEY` | 下記で生成した値（1つ目） |
| `UNSUBSCRIBE_SECRET` | 同（2つ目） |
| `TRACKING_SECRET` | 同（3つ目） |

**シークレット生成（3回実行して3つ取得）:**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**重要:** `railway link` で紐づけるのは「プロジェクト」です。変数は **Web サービス（アプリ）の Variables** に設定してください。サービスがまだない場合は、次の手順6で初回デプロイするとサービスができ、そのサービスの Variables に上記を設定します。

---

### 6. 初回デプロイ（CLI からアップロード）

MA- のフォルダで:

```bash
cd /Users/okazakikatsuhiro/MA-

# デプロイ（現在のフォルダのコードが Railway に送られ、ビルド・起動します）
railway up
```

初回はサービスが自動作成され、ビルド・デプロイが始まります。**手順5の環境変数は、この「Web サービス」の Variables に設定してください。**

デプロイが失敗する場合は、Dashboard の **Deployments** → ログでエラーを確認し、主に **Variables の不足・誤り** を確認してください。

---

### 7. 公開 URL を発行

1. Dashboard で、MA- の **Web サービス**をクリック
2. **「Settings」** → **「Networking」** → **「Generate Domain」** をクリック
3. 表示された URL（例: `xxxx.up.railway.app`）が本番のアドレスです
4. 同じサービスの **「Variables」** に追加:  
   - 変数名: `BASE_URL`  
   - 値: `https://（表示されたドメイン）`  
   例: `https://ma-tool-production.up.railway.app`
5. 必要なら **「Redeploy」** で再デプロイ

---

### 8. マイグレーションと初期ユーザー（初回のみ）

デプロイが成功したら、同じ MA- フォルダで:

```bash
railway run uv run alembic upgrade head
railway run uv run python -m src.ma_tool.seed   # 必要なら
```

ブラウザで **Generate Domain で発行した URL** にアクセスし、ログインできるか確認してください。

---

## 今後の更新（修正を本番に反映する）

GitHub 連携を使わない場合、**コードを直したら同じフォルダで再度 `railway up`** すると、その内容が本番にデプロイされます。

```bash
cd /Users/okazakikatsuhiro/MA-
git pull   # 必要なら最新を取得
railway up
```

後から「Configure GitHub App」でリポジトリを許可し、同じプロジェクトに **GitHub Repo を追加**すれば、push で自動デプロイに切り替えることもできます。

---

## まとめ

| 作業 | 方法 |
|------|------|
| プロジェクト作成 | Dashboard で **New Project** → **Empty Project** |
| DB | 同じプロジェクトで **+ New** → **Add PostgreSQL** |
| コードのデプロイ | ローカルで `railway link` → **Variables を Dashboard で設定** → `railway up` |
| URL | 該当サービスの **Settings** → **Generate Domain** |
| 今後の反映 | 同じフォルダで `railway up`（または後から GitHub 連携を追加） |

これで、リポジトリが一覧に表示されなくても MA- を本番環境にデプロイできます。
