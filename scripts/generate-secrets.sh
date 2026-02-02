#!/bin/bash
# セキュリティシークレットを生成するスクリプト

echo "=== セキュリティシークレット生成 ==="
echo ""
echo "以下のシークレットを .env ファイルに設定してください:"
echo ""
echo "SESSION_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
echo "UNSUBSCRIBE_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
echo "TRACKING_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
echo ""
echo "=== 生成完了 ==="
