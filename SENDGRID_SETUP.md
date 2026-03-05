# メール機能（SendGrid）の有効化手順

この MA ツールでメール送信を使うには、**SendGrid の API キー** と **送信元アドレス** を設定します。  
別サービスで同じ SendGrid アカウント・同じドメインを使っている場合も、同じ手順でこのサービスから送信できます。

---

## 前提

- SendGrid アカウントがあること
- 送信に使う **ドメイン** が SendGrid で認証済みであること（SPF / DKIM 等）
- 本番環境は **Railway** の **Bizcraft MA-** サービスを想定

---

## 手順

### 1. SendGrid で API キーを用意する

1. [SendGrid Dashboard](https://app.sendgrid.com/) にログイン
2. **Settings** → **API Keys** を開く
3. **Create API Key** をクリック
4. 名前を入力（例: `MA Tool (Bizcraft)`）
5. 権限は **Restricted Access** で、**Mail Send** の **Full Access** にチェック（または **Full Access** で作成）
6. **Create & View** をクリック
7. 表示された **API Key** をコピー（この画面を閉じると二度と表示されません）

※ 既存の API キーを流用しても動きますが、運用上は「この MA ツール専用」のキーを 1 本作ることを推奨します。

---

### 2. Railway に環境変数を設定する

1. [Railway Dashboard](https://railway.app) で **Bizcraft MA-** プロジェクトを開く
2. **Bizcraft MA-**（Web サービス）をクリック
3. **Variables** タブを開く
4. 次の変数を追加（既にある場合は編集）

| 変数名 | 値 | 必須 |
|--------|-----|------|
| `SENDGRID_API_KEY` | 手順1でコピーした API キー | ✅ |
| `MAIL_FROM` | 送信元メールアドレス（認証済みドメイン）<br>例: `noreply@yourdomain.com` | ✅ |
| `MAIL_REPLY_TO` | 返信先アドレス（任意）<br>例: `support@yourdomain.com` | 任意 |

5. **保存** する（Variables は保存後、次回リクエストから反映されます）

---

### 3. 本番環境であることを確認する

メールは **本番モード** のときだけ実際の宛先に送信されます。以下を確認してください。

- **`APP_ENV`** が **`prod`** になっていること（本番用にデプロイしている場合は通常 `prod`）
- 本番では **`MAIL_REDIRECT_TO`** は **設定しない**（未設定で OK）。  
  ※ `MAIL_REDIRECT_TO` を設定すると、すべてのメールがそのアドレスに転送され、本来の宛先には届きません（dev/staging 用の機能です）。

---

### 4. デプロイの反映（必要なら）

- Variables を **追加・変更しただけ** なら、多くの場合 **そのまま** で反映されます
- 反映されない場合は **Redeploy** を 1 回実行してください  
  - Railway の **Deployments** タブ → **Redeploy**

---

### 5. 動作確認

1. アプリにログインし、**シナリオ** でメールが送信される条件を満たすリードを用意する  
   または **イベント** からテスト送信できる機能があればそれを使う
2. 送信が実行されたあと、**SendGrid** の **Activity** で配信・開封が記録されているか確認
3. Railway の **ログ** に `SendGrid not configured` が出ていなければ、メール設定は有効になっています

---

## 設定値の例（本番）

```env
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MAIL_FROM=noreply@yourdomain.com
MAIL_REPLY_TO=support@yourdomain.com
```

- **MAIL_FROM** は、SendGrid で認証済みのドメインのアドレスにしてください（別サービスで使っている同じドメインで問題ありません）
- **MAIL_REPLY_TO** は空でも動作します

---

## よくある質問

**Q. 同じ SendGrid アカウント・同じドメインで別サービスも送っているが、この MA ツールからも送ってよい？**  
A. はい。同じアカウント・同じ認証済みドメインで、このサービスからも送信して問題ありません。送信枠はアカウントで共有されます。

**Q. 本番でテスト用に、いったんすべてのメールを自分に転送したい**  
A. 本番では **MAIL_REDIRECT_TO** は使わないことを推奨します。テストは SendGrid のダミー宛先や、テスト用リードだけで行ってください。

**Q. 開封・クリック計測は？**  
A. メール本文に **トラッキング用 URL**（`/t/open/...`, `/t/c/...`）が埋め込まれていれば、SendGrid を設定したうえで実際にメールを送ると、開封・クリックが記録され、リードのステータスにも反映されます。  
SendGrid の **Event Webhook**（開封・クリックイベント）を MA ツールの `/webhooks/sendgrid` に送る設定をすると、さらに確実に記録できます（任意）。

---

## まとめ

| やること | 場所 |
|----------|------|
| API キーを取得 | SendGrid → Settings → API Keys |
| 環境変数を設定 | Railway → Bizcraft MA- → Variables |
| 本番は APP_ENV=prod、MAIL_REDIRECT_TO は未設定 | 同上 |
| 必要なら Redeploy | Railway → Deployments |

ここまで設定すれば、この MA ツールから同じドメインでメール送信が可能になります。
