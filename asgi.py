"""Production ASGI entry point (referenced by ``uvicorn asgi:app`` / Gunicorn)."""

from dotenv import load_dotenv

load_dotenv()

from presentation.fastapi.app import create_app  # noqa: E402

app = create_app()
