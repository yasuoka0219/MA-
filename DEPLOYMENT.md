# 本番環境への実装手順

## 📋 前提条件

- PostgreSQL データベース（本番環境）
- Python 3.11以上
- サーバー（VPS、クラウドなど）
- ドメイン（オプション、推奨）

---

## 🔐 1. 環境変数の設定

本番環境用の環境変数を設定します。`.env`ファイルを作成するか、サーバーの環境変数として設定してください。

### 必須環境変数

```bash
# データベース接続
DATABASE_URL=postgresql://username:password@host:port/database_name

# アプリケーション環境
APP_ENV=prod

# セッション管理（強力なランダム文字列を生成）
SESSION_SECRET_KEY=your-very-long-random-secret-key-here-minimum-32-characters

# セキュリティシークレット（強力なランダム文字列を生成）
UNSUBSCRIBE_SECRET=your-strong-random-secret-for-unsubscribe
TRACKING_SECRET=your-strong-random-secret-for-tracking

# ベースURL（本番環境のURL）
BASE_URL=https://your-domain.com

# メール送信設定
SENDGRID_API_KEY=your-sendgrid-api-key
MAIL_FROM=noreply@your-domain.com
MAIL_REPLY_TO=support@your-domain.com
# 本番環境ではMAIL_REDIRECT_TOは不要（実際に送信される）

# LINE設定（使用する場合）
LINE_CHANNEL_ACCESS_TOKEN=your-line-channel-access-token
LINE_CHANNEL_SECRET=your-line-channel-secret
LINE_FRIEND_ADD_URL=https://line.me/R/ti/p/@your-line-id

# スケジューラー設定
SCHEDULER_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
```

### セキュリティシークレットの生成方法

```bash
# Pythonで強力なシークレットを生成
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 🗄️ 2. データベースのセットアップ

### PostgreSQLデータベースの作成

```bash
# PostgreSQLに接続
psql -U postgres

# データベースとユーザーを作成
CREATE DATABASE ma_tool_prod;
CREATE USER ma_tool_user WITH PASSWORD 'strong_password_here';
GRANT ALL PRIVILEGES ON DATABASE ma_tool_prod TO ma_tool_user;
\q
```

### データベース接続URLの形式

```
postgresql://ma_tool_user:strong_password_here@localhost:5432/ma_tool_prod
```

---

## 📦 3. アプリケーションのデプロイ

### 方法A: サーバーに直接デプロイ

```bash
# 1. サーバーにSSH接続
ssh user@your-server

# 2. プロジェクトディレクトリに移動
cd /path/to/MA-

# 3. Gitから最新コードを取得（Gitを使用している場合）
git pull origin main

# 4. 依存関係のインストール
uv pip install -r pyproject.toml

# 5. 環境変数の設定
# .envファイルを作成または環境変数を設定
nano .env  # 上記の環境変数を設定

# 6. データベースマイグレーションの実行
uv run alembic upgrade head

# 7. 初期ユーザーの作成（必要に応じて）
uv run python -m src.ma_tool.seed
```

### 方法B: systemdサービスとして起動（推奨）

`/etc/systemd/system/ma-tool.service` を作成:

```ini
[Unit]
Description=MA Tool FastAPI Application
After=network.target postgresql.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/MA-
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn src.ma_tool.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

サービスを有効化:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ma-tool
sudo systemctl start ma-tool
sudo systemctl status ma-tool
```

---

## 🌐 4. リバースプロキシの設定（Nginx）

### Nginx設定例

`/etc/nginx/sites-available/ma-tool` を作成:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # HTTPSにリダイレクト（Let's Encrypt使用時）
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # セキュリティヘッダー
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocketサポート（必要に応じて）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 静的ファイル（必要に応じて）
    location /static {
        alias /path/to/MA-/static;
    }
}
```

設定を有効化:

```bash
sudo ln -s /etc/nginx/sites-available/ma-tool /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔒 5. SSL証明書の設定（Let's Encrypt）

```bash
# Certbotのインストール
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# SSL証明書の取得
sudo certbot --nginx -d your-domain.com

# 自動更新の確認
sudo certbot renew --dry-run
```

---

## ✅ 6. 本番環境の確認チェックリスト

### セキュリティ設定

- [ ] `APP_ENV=prod` が設定されている
- [ ] `SESSION_SECRET_KEY` が強力なランダム文字列に設定されている
- [ ] `UNSUBSCRIBE_SECRET` が `change-me-in-production` から変更されている
- [ ] `TRACKING_SECRET` が `change-me-in-production` から変更されている
- [ ] データベースパスワードが強力である
- [ ] `.env`ファイルの権限が適切に設定されている（`chmod 600 .env`）

### データベース

- [ ] マイグレーションが正常に実行された
- [ ] 初期ユーザーが作成された
- [ ] データベースのバックアップ戦略が確立されている

### アプリケーション

- [ ] アプリケーションが正常に起動している
- [ ] ログインが動作している
- [ ] メール送信が動作している（本番環境でテスト）
- [ ] LINE連携が動作している（使用する場合）

### インフラ

- [ ] Nginxが正常に動作している
- [ ] SSL証明書が有効である
- [ ] ファイアウォール設定が適切である
- [ ] ログローテーションが設定されている

---

## 🔄 7. 更新手順

本番環境を更新する場合:

```bash
# 1. サーバーにSSH接続
ssh user@your-server

# 2. アプリケーションを停止
sudo systemctl stop ma-tool

# 3. コードを更新
cd /path/to/MA-
git pull origin main  # または最新コードを配置

# 4. 依存関係を更新
uv pip install -r pyproject.toml

# 5. マイグレーションを実行
uv run alembic upgrade head

# 6. アプリケーションを再起動
sudo systemctl start ma-tool

# 7. ログを確認
sudo journalctl -u ma-tool -f
```

---

## 📊 8. 監視とログ

### ログの確認

```bash
# systemdサービスのログ
sudo journalctl -u ma-tool -f

# Nginxのログ
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### パフォーマンス監視

- サーバーのリソース使用状況を監視
- データベースの接続数を監視
- アプリケーションのレスポンスタイムを監視

---

## 🚨 9. トラブルシューティング

### アプリケーションが起動しない

```bash
# ログを確認
sudo journalctl -u ma-tool -n 50

# 環境変数を確認
env | grep -E "DATABASE_URL|APP_ENV|SESSION_SECRET_KEY"

# 手動で起動してエラーを確認
cd /path/to/MA-
uv run uvicorn src.ma_tool.main:app --host 0.0.0.0 --port 8000
```

### データベース接続エラー

- データベースが起動しているか確認
- 接続情報（URL、ユーザー名、パスワード）を確認
- ファイアウォール設定を確認

### マイグレーションエラー

```bash
# 現在のマイグレーション状態を確認
uv run alembic current

# マイグレーション履歴を確認
uv run alembic history

# 特定のバージョンにロールバック（必要に応じて）
uv run alembic downgrade <revision>
```

---

## 📝 10. バックアップ戦略

### データベースのバックアップ

```bash
# 日次バックアップスクリプト例
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U ma_tool_user ma_tool_prod > /backup/ma_tool_$DATE.sql

# 古いバックアップの削除（30日以上）
find /backup -name "ma_tool_*.sql" -mtime +30 -delete
```

### cronジョブの設定

```bash
# 毎日午前2時にバックアップ
0 2 * * * /path/to/backup-script.sh
```

---

## 🔐 11. セキュリティベストプラクティス

1. **ファイアウォール設定**
   ```bash
   # UFWの設定例
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow 80/tcp     # HTTP
   sudo ufw allow 443/tcp    # HTTPS
   sudo ufw enable
   ```

2. **定期的なセキュリティ更新**
   ```bash
   sudo apt-get update
   sudo apt-get upgrade
   ```

3. **ログの監視**
   - 異常なアクセスパターンを監視
   - 失敗したログイン試行を監視

4. **データベースのセキュリティ**
   - 強力なパスワードを使用
   - 必要最小限の権限を付与
   - 定期的なバックアップ

---

## 📞 12. サポート

問題が発生した場合:
1. ログを確認
2. 環境変数を確認
3. データベース接続を確認
4. ネットワーク設定を確認

---

## 📚 参考情報

- FastAPI公式ドキュメント: https://fastapi.tiangolo.com/
- Alembicドキュメント: https://alembic.sqlalchemy.org/
- Nginxドキュメント: https://nginx.org/en/docs/
- Let's Encrypt: https://letsencrypt.org/
