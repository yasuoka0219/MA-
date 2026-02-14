#!/usr/bin/env python3
"""
指定したメールアドレスのユーザーのパスワードをリセットします。
管理者がログイン情報を忘れた場合に、サーバー上で実行してください。

使用例（プロジェクトルートで）:
  .venv/bin/python scripts/reset_user_password.py --email admin@example.com --password "新しいパスワード"
  .venv/bin/python scripts/reset_user_password.py --email admin@example.com   # パスワードを対話入力

環境変数 DATABASE_URL が必要です。.env を読み込む場合は実行前に export するか、
  python -c "from dotenv import load_dotenv; load_dotenv()" などで読み込んでから実行してください。
"""
import argparse
import sys
from pathlib import Path

# プロジェクトルートを path に追加
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.user import User
from src.ma_tool.services.password import hash_password


def main():
    parser = argparse.ArgumentParser(
        description="指定ユーザーのパスワードをリセット（管理者パスワード忘れ時用）"
    )
    parser.add_argument("--email", required=True, help="パスワードをリセットするユーザーのメールアドレス")
    parser.add_argument("--password", default=None, help="新しいパスワード（未指定の場合は対話入力）")
    args = parser.parse_args()

    password = args.password
    if not password:
        try:
            import getpass
            password = getpass.getpass("新しいパスワードを入力: ")
            password_confirm = getpass.getpass("確認のため再入力: ")
            if password != password_confirm:
                print("エラー: パスワードが一致しません。", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"エラー: パスワード入力に失敗しました: {e}", file=sys.stderr)
            sys.exit(1)

    if len(password) < 8:
        print("エラー: パスワードは8文字以上にしてください。", file=sys.stderr)
        sys.exit(1)

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user:
            print(f"エラー: メールアドレス '{email}' のユーザーが見つかりません。", file=sys.stderr)
            sys.exit(1)
        user.password_hash = hash_password(password)
        db.commit()
        print(f"完了: {email} のパスワードを更新しました。")
    except Exception as e:
        db.rollback()
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
