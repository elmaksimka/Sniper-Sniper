from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.dependencies import SystemHealthServiceDependency
from app.api.routes import router
from app.core.config import get_settings
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
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
