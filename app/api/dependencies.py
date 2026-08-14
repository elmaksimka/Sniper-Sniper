import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
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
from app.services.copy_grade_dashboard_service import CopyGradeDashboardService
from app.services.copy_source_service import CopySourceService
from app.services.paper_copy_dashboard_service import PaperCopyDashboardService
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.funding_service import FundingService
from app.services.token_score_snapshot_service import TokenScoreSnapshotService


SessionDependency = Annotated[AsyncSession, Depends(get_session)]

admin_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def require_admin_access(
    api_key: Annotated[str | None, Security(admin_api_key_header)],
) -> None:
    settings = get_settings()
    if settings.environment.lower() != "production":
        return
    if api_key is None or not secrets.compare_digest(
        api_key,
        settings.admin_api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


AdminAccessDependency = Annotated[None, Depends(require_admin_access)]


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


def get_token_score_snapshot_service(
    session: SessionDependency,
) -> TokenScoreSnapshotService:
    return TokenScoreSnapshotService(session)


TokenScoreSnapshotServiceDependency = Annotated[
    TokenScoreSnapshotService,
    Depends(get_token_score_snapshot_service),
]


def get_alert_service(session: SessionDependency) -> AlertService:
    return AlertService(session)


AlertServiceDependency = Annotated[AlertService, Depends(get_alert_service)]


def get_funding_service(session: SessionDependency) -> FundingService:
    return FundingService(session)


FundingServiceDependency = Annotated[
    FundingService,
    Depends(get_funding_service),
]


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


def get_copy_grade_dashboard_service(
    session: SessionDependency,
) -> CopyGradeDashboardService:
    settings = get_settings()
    return CopyGradeDashboardService(
        HeartbeatRepository(session),
        settings.candidate_enrichment_maximum_history_transactions,
        WalletRepository(session),
    )


CopyGradeDashboardServiceDependency = Annotated[
    CopyGradeDashboardService,
    Depends(get_copy_grade_dashboard_service),
]


async def get_paper_copy_dashboard_service(
    session: SessionDependency,
) -> PaperCopyDashboardService:
    settings = get_settings()
    dynamic_sources = await CopySourceService(
        HeartbeatRepository(session),
        scores=ScoreSnapshotRepository(session),
    ).list_addresses()
    return PaperCopyDashboardService(
        session,
        settings.paper_copy_portfolio_wallet,
        dynamic_sources or settings.paper_copy_sources,
    )


PaperCopyDashboardServiceDependency = Annotated[
    PaperCopyDashboardService,
    Depends(get_paper_copy_dashboard_service),
]
