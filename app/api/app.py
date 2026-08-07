from collections.abc import AsyncIterator
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.dependencies import SystemHealthServiceDependency
from app.api.routes import router
from app.api.schemas import BuildInfo
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.database import engine
from app.listeners.helius_client import HeliusClient


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    helius_client = HeliusClient()
    helius_client.max_retries = 0
    application.state.helius_client = helius_client
    try:
        yield
    finally:
        await helius_client.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    production = settings.environment.lower() == "production"
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    allowed_hosts = [
        host.strip()
        for host in settings.allowed_hosts.split(",")
        if host.strip()
    ]
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts,
    )
    logger = structlog.get_logger("api")

    @application.middleware("http")
    async def harden_http_edge(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if 0 < len(supplied_request_id) <= 128
            and all(
                character.isascii()
                and (character.isalnum() or character in "-_.")
                for character in supplied_request_id
            )
            else uuid4().hex
        )
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started_at = monotonic()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=()"
            )
            if production:
                response.headers["Content-Security-Policy"] = (
                    "default-src 'none'; frame-ancestors 'none'"
                )
            logger.info(
                "http_request_complete",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((monotonic() - started_at) * 1000, 3),
            )
            return response
        except Exception:
            logger.exception(
                "http_request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((monotonic() - started_at) * 1000, 3),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/version", response_model=BuildInfo, tags=["system"])
    async def version() -> BuildInfo:
        return BuildInfo(
            version=settings.app_version,
            revision=settings.git_sha,
            environment=settings.environment,
        )

    @application.get("/health/live", tags=["system"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["system"])
    async def readiness(
        service: SystemHealthServiceDependency,
    ) -> JSONResponse:
        report = await service.readiness()
        status_code = (
            status.HTTP_200_OK
            if report["status"] == "ready"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            content=jsonable_encoder(report),
            status_code=status_code,
        )

    application.include_router(router)
    return application


app = create_app()
