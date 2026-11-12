"""Development entry point.

In production, use ``uvicorn asgi:app`` (or Gunicorn + UvicornWorker).

To start in development::

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
        # Client address resolution is done in one place: the app (TRUSTED_PROXY_HOPS).
        # By default uvicorn trusts X-Forwarded-For from loopback and rewrites
        # scope["client"] to its **leftmost value**, so a local request alone could
        # put an arbitrary IP into the audit log (ADR-0075 §1).
        proxy_headers=False,
    )
