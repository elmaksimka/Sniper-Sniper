from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database import get_session
from app.services.alert_service import AlertService
from app.services.analytics_service import AnalyticsService
from app.services.monitor_service import MonitorService
from app.services.read_service import ReadService
from app.services.score_snapshot_service import ScoreSnapshotService
from app.services.scoring_service import ScoringService
from app.services.system_health_service import SystemHealthService


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


def get_scoring_service(session: SessionDependency) -> ScoringService:
    return ScoringService(session)


ScoringServiceDependency = Annotated[
    ScoringService,
    Depends(get_scoring_service),
]


def get_score_snapshot_service(
    session: SessionDependency,
) -> ScoreSnapshotService:
    return ScoreSnapshotService(session)


ScoreSnapshotServiceDependency = Annotated[
    ScoreSnapshotService,
    Depends(get_score_snapshot_service),
]


def get_alert_service(session: SessionDependency) -> AlertService:
    return AlertService(session)


AlertServiceDependency = Annotated[AlertService, Depends(get_alert_service)]


def get_monitor_service(session: SessionDependency) -> MonitorService:
    return MonitorService(session)


MonitorServiceDependency = Annotated[
    MonitorService,
    Depends(get_monitor_service),
]


def get_system_health_service(
    request: Request,
    session: SessionDependency,
) -> SystemHealthService:
    settings = get_settings()
    return SystemHealthService(
        session,
        helius_client=request.app.state.helius_client,
        worker_stale_after_seconds=settings.worker_heartbeat_stale_seconds,
        check_timeout_seconds=settings.readiness_check_timeout_seconds,
    )


SystemHealthServiceDependency = Annotated[
    SystemHealthService,
    Depends(get_system_health_service),
]
