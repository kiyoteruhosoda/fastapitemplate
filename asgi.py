"""本番用 ASGI エントリポイント（``uvicorn asgi:app`` / Gunicorn から参照）。"""

from dotenv import load_dotenv

load_dotenv()

from presentation.fastapi.app import create_app  # noqa: E402

app = create_app()
