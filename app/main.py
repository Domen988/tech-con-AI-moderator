from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.routers import api, ws

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(title="AI Conference Moderator", version="0.1.0")

    # Routers
    app.include_router(api.router)
    app.include_router(ws.router)

    # Static files
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(BASE_DIR / "templates" / "index.html"))

    return app
