#!/usr/bin/env python3
"""AI Conference Moderator PoC — entry point."""

import uvicorn
from app.config import settings

settings.print_status()

from app.main import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "run:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
