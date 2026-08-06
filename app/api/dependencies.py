from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.services.analytics_service import AnalyticsService
from app.services.read_service import ReadService


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_read_service(session: SessionDependency) -> ReadService:
    return ReadService(session)


ReadServiceDependency = Annotated[ReadService, Depends(get_read_service)]


def get_analytics_service(session: SessionDependency) -> AnalyticsService:
    return AnalyticsService(session)


AnalyticsServiceDependency = Annotated[
    AnalyticsService,
    Depends(get_analytics_service),
]
