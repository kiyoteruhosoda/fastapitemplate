"""開発用エントリポイント。

本番では ``uvicorn asgi:app``（または Gunicorn + UvicornWorker）を使用すること。

開発時の起動方法::

    uv run python main.py
"""

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "asgi:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        # 接続元の判定はアプリ側（TRUSTED_PROXY_HOPS）に一本化する。
        # uvicorn の既定はループバックからの X-Forwarded-For を信用して
        # scope["client"] を**左端の値**に書き換えるため、手元で叩くだけで
        # 監査ログに任意の IP を入れられてしまう（ADR-0013）。
        proxy_headers=False,
    )
