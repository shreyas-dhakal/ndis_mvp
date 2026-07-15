import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from starlette.requests import Request

from app.routes.ingest import router as ingest_router
from app.routes.retrieve import router as retrieve_router
from app.routes.debug import router as debug_router
from app.routes.agent import router as agent_router
from app.routes.documents import router as documents_router
from app.routes.inference import router as inference_router

from app.core.config import LOG_DIR, LOG_LEVEL
from app.core.logging_setup import setup_logging
from app.db.pgvector_adapter import close_pool, open_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    open_pool()
    try:
        yield
    finally:
        close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Data Spine", version="0.1.0", lifespan=lifespan)

    logger = logging.getLogger("app")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            status_code = getattr(response, "status_code", "???")
            logger.info(f"{request.method} {request.url.path} -> {status_code} ({elapsed_ms:.1f}ms)")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(ingest_router)
    app.include_router(retrieve_router)
    app.include_router(debug_router)
    app.include_router(agent_router)
    app.include_router(documents_router)
    app.include_router(inference_router)
    return app


def main() -> None:
    activity_name = os.getenv("ACTIVITY_NAME") or datetime.now().strftime("api_%Y%m%d_%H%M%S")
    log_path = setup_logging(log_dir=LOG_DIR, activity_name=activity_name, log_level=LOG_LEVEL)
    print(f"Log file: {log_path}")

    port = int(os.getenv("PORT", "8000"))
    print(f"Starting API on http://0.0.0.0:{port}")
    uvicorn.run("app.main:create_app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
