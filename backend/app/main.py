import time

from fastapi import FastAPI, Request

from app.api.routes import router
from app.api.zo_routes import zo_router
from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router, prefix=settings.api_prefix)
app.include_router(zo_router, prefix=settings.api_prefix)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.api(request.method, request.url.path, "request received")
    started_at = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - started_at) * 1000)
    logger.api(
        request.method,
        request.url.path,
        f"response {response.status_code} ({duration_ms}ms)",
    )
    return response


@app.get("/health", include_in_schema=False)
async def root_health() -> dict[str, str]:
    return {"status": "ok"}
