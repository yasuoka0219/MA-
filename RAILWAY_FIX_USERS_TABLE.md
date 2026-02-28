# Railway：`users` テーブルがない 500 エラーの直し方

ログの **`relation "users" does not exist`** は、DB にマイグレーションがかかっていないためです。  
Railway の **pre-deploy ステップ**でマイグレーションを実行すると解消できます。

---

## 手順

### 1. Pre-deploy ステップを追加する

1. Railway Dashboard → **Bizcraft MA-** サービスをクリック
2. **Settings** タブを開く
3. **Deploy** のところにある **「+ Add pre-deploy step」** をクリック
4. 表示された入力欄に、次の**どちらか**を入力（まずは A を試す）

   **A. uv を使う場合**
   ```bash
   uv run alembic upgrade head
   ```

   **B. A で失敗する場合（uv が無いとき）**
   ```bash
   alembic upgrade head
   ```
   または
   ```bash
   python -m alembic upgrade head
   ```

5. **保存**する

### 2. 再デプロイする

1. **Deployments** タブを開く
2. **「Redeploy」** または **「Deploy」** をクリック
3. ビルド → **pre-deploy（マイグレーション）** → 起動の順で実行されるので、完了まで待つ
4. ログで `alembic upgrade head` が成功しているか確認する

### 3. 動作確認

1. ブラウザで `https://bizcraft-ma-production.up.railway.app/ui/login` を開く
2. **Internal Server Error** ではなく、ログイン画面が出れば OK
3. まだユーザーがいない場合は、あとで seed で作成する

---

## 補足

- **Pre-deploy** は「デプロイのたびに、起動前に 1 回だけ」実行されます。Railway のサーバー上で動くので、`postgres.railway.internal` にも接続できます。
- 今後マイグレーションを追加したときも、同じ pre-deploy で自動的に適用されます。
- **Start Command** は `sh scripts/start.sh` のままで問題ありません（起動時にもマイグレーションを走らせたい場合）。pre-deploy だけでも構いません。
