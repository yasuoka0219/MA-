# Railway：Web サービスの Variables の設定手順

`DATABASE_URL`, `APP_ENV`, `SESSION_SECRET_KEY`, `UNSUBSCRIBE_SECRET`, `TRACKING_SECRET` を、**Web サービス**（`railway up` でデプロイしたアプリ）の Variables に設定する方法です。

---

## 1. Web サービスを開く

1. [Railway Dashboard](https://railway.app) にログイン
2. **MA- 用のプロジェクト**をクリック
3. プロジェクト内に **2 つのサービス** があるはずです：
   - **PostgreSQL**（データベースのアイコン）
   - **Web サービス**（アプリ用。名前はプロジェクト名や "Web" など）
4. **PostgreSQL ではなく、もう一方の Web サービス**のカードをクリック

※ まだ `railway up` を実行していない場合は、先に `railway up` を 1 回実行すると Web サービスが自動作成されます。そのあとで同じ手順で開きます。

---

## 2. Variables タブを開く

1. Web サービスを開いた状態で、画面上部またはタブの **「Variables」** をクリック
2. 環境変数を追加・編集する画面になります

---

## 3. 変数を 1 つずつ追加する

**「+ New Variable」** または **「Add Variable」** をクリックし、次の 5 つを追加します。

### ① DATABASE_URL

- **Key（変数名）:** `DATABASE_URL`
- **Value（値）:** PostgreSQL の接続文字列

**値の取り方：**

1. プロジェクト内の **PostgreSQL** のサービスをクリック
2. **「Variables」** タブを開く
3. **`DATABASE_URL`** の **値**（長い文字列）をコピー
4. Web サービスの Variables に戻り、Key に `DATABASE_URL`、Value にその文字列を貼り付け

（PostgreSQL の `DATABASE_URL` を、そのまま Web サービスにも設定します。）

---

### ② APP_ENV

- **Key:** `APP_ENV`
- **Value:** `prod`

---

### ③ SESSION_SECRET_KEY

- **Key:** `SESSION_SECRET_KEY`
- **Value:** 下の「シークレットの生成」で作った **1 つ目** の文字列

---

### ④ UNSUBSCRIBE_SECRET

- **Key:** `UNSUBSCRIBE_SECRET`
- **Value:** シークレットの **2 つ目**

---

### ⑤ TRACKING_SECRET

- **Key:** `TRACKING_SECRET`
- **Value:** シークレットの **3 つ目**

---

## 4. シークレットの生成（3 つ分）

ターミナルで、次のコマンドを **3 回** 実行します。毎回違う文字列が出るので、それぞれメモします。

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

例（実際の値は毎回変わります）:
- 1 回目 → `SESSION_SECRET_KEY` に貼り付け
- 2 回目 → `UNSUBSCRIBE_SECRET` に貼り付け
- 3 回目 → `TRACKING_SECRET` に貼り付け

---

## 5. Raw Editor でまとめて入れる場合

Variables 画面に **「Raw Editor」** がある場合、次の形式でまとめて貼り付けることもできます。

```
DATABASE_URL=postgresql://postgres:xxxxx@xxxxx.railway.app:5432/railway
APP_ENV=prod
SESSION_SECRET_KEY=（1つ目の生成した文字列）
UNSUBSCRIBE_SECRET=（2つ目の生成した文字列）
TRACKING_SECRET=（3つ目の生成した文字列）
```

- `DATABASE_URL` だけは、PostgreSQL の Variables からコピーした**実際の値**に置き換えてください。
- 3 つのシークレットは、上記コマンドで生成した**実際の値**に置き換えてください。

---

## 6. 保存と確認

- 1 つずつ追加する場合は、各変数ごとに **保存** または **チェックマーク** を押す
- Raw Editor の場合は **Save** で一括保存
- 一覧に 5 つ（`DATABASE_URL`, `APP_ENV`, `SESSION_SECRET_KEY`, `UNSUBSCRIBE_SECRET`, `TRACKING_SECRET`）並んでいれば OK です

---

## 7. デプロイし直す（必要なとき）

Variables を追加・変更したあと、アプリを再起動したい場合は次のどちらかです。

- Web サービスの **「Deployments」** タブで **「Redeploy」** をクリック  
または  
- ローカルで再度 `railway up` を実行

これで、Web サービスの Variables に 5 つが設定された状態で本番が動きます。
