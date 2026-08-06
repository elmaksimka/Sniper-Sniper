from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import (
    AlertServiceDependency,
    AnalyticsServiceDependency,
    MonitorServiceDependency,
    ReadServiceDependency,
    ScoreSnapshotServiceDependency,
    ScoringServiceDependency,
)
from app.api.schemas import (
    AlertPage,
    AlertRead,
    MonitorCreate,
    MonitorPage,
    MonitorRead,
    TokenAnalyticsRead,
    TokenPage,
    TokenRead,
    TradePage,
    TradeRead,
    TokenPositionRead,
    WalletPage,
    WalletRead,
    WalletAnalyticsRead,
    WalletPositionsRead,
    WalletScoreRead,
    WalletScoreLeaderboardPage,
    WalletScoreSnapshotRead,
)


router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/tokens", response_model=TokenPage)
async def list_tokens(
    service: ReadServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
    creator: str | None = None,
) -> TokenPage:
    tokens, total = await service.list_tokens(limit, offset, creator)
    return TokenPage(
        items=[TokenRead.model_validate(token) for token in tokens],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tokens/{address}", response_model=TokenRead)
async def get_token(
    address: str,
    service: ReadServiceDependency,
) -> TokenRead:
    token = await service.get_token(address)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    return TokenRead.model_validate(token)


@router.get("/wallets", response_model=WalletPage)
async def list_wallets(
    service: ReadServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> WalletPage:
    wallets, total = await service.list_wallets(limit, offset)
    return WalletPage(
        items=[WalletRead.model_validate(wallet) for wallet in wallets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/wallets/{address}", response_model=WalletRead)
async def get_wallet(
    address: str,
    service: ReadServiceDependency,
) -> WalletRead:
    wallet = await service.get_wallet(address)
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    return WalletRead.model_validate(wallet)


@router.get("/trades", response_model=TradePage)
async def list_trades(
    service: ReadServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
    token_address: str | None = None,
    wallet_address: str | None = None,
    side: Literal["buy", "sell"] | None = None,
) -> TradePage:
    trades, total = await service.list_trades(
        limit,
        offset,
        token_address,
        wallet_address,
        side,
    )
    return TradePage(
        items=[TradeRead.from_trade(trade) for trade in trades],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/analytics/wallets/{address}",
    response_model=WalletAnalyticsRead,
)
async def get_wallet_analytics(
    address: str,
    service: AnalyticsServiceDependency,
) -> WalletAnalyticsRead:
    analytics = await service.get_wallet(address)
    if analytics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    return WalletAnalyticsRead.model_validate(analytics)


@router.get(
    "/analytics/tokens/{address}",
    response_model=TokenAnalyticsRead,
)
async def get_token_analytics(
    address: str,
    service: AnalyticsServiceDependency,
) -> TokenAnalyticsRead:
    analytics = await service.get_token(address)
    if analytics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    return TokenAnalyticsRead.model_validate(analytics)


@router.get(
    "/analytics/wallets/{address}/positions",
    response_model=WalletPositionsRead,
)
async def get_wallet_positions(
    address: str,
    service: AnalyticsServiceDependency,
    include_closed: bool = False,
) -> WalletPositionsRead:
    positions = await service.get_wallet_positions(address, include_closed)
    if positions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    items = [TokenPositionRead.model_validate(position) for position in positions]
    return WalletPositionsRead(
        wallet_address=address,
        items=items,
        total=len(items),
    )


@router.get(
    "/scores/wallets/{address}",
    response_model=WalletScoreRead,
)
async def get_wallet_score(
    address: str,
    service: ScoringServiceDependency,
) -> WalletScoreRead:
    score = await service.score_wallet(address)
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    return WalletScoreRead.model_validate(score)


@router.get(
    "/scores/wallets",
    response_model=WalletScoreLeaderboardPage,
)
async def list_wallet_scores(
    service: ScoreSnapshotServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
    grade: Literal["A", "B", "C", "D", "E"] | None = None,
) -> WalletScoreLeaderboardPage:
    snapshots, total = await service.leaderboard(limit, offset, grade)
    return WalletScoreLeaderboardPage(
        items=[
            WalletScoreSnapshotRead.from_snapshot(snapshot)
            for snapshot in snapshots
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts", response_model=AlertPage)
async def list_alerts(
    service: AlertServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
    entity_address: str | None = None,
    severity: Literal["high", "critical"] | None = None,
    acknowledged: bool | None = None,
) -> AlertPage:
    alerts, total = await service.list_alerts(
        limit,
        offset,
        entity_address,
        severity,
        acknowledged,
    )
    return AlertPage(
        items=[AlertRead.from_alert(alert) for alert in alerts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertRead,
)
async def acknowledge_alert(
    alert_id: int,
    service: AlertServiceDependency,
) -> AlertRead:
    alert = await service.acknowledge(alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    return AlertRead.from_alert(alert)


@router.get("/monitors", response_model=MonitorPage)
async def list_monitors(
    service: MonitorServiceDependency,
    enabled_only: bool = False,
) -> MonitorPage:
    monitors = await service.list(enabled_only)
    return MonitorPage(
        items=[MonitorRead.from_monitor(monitor) for monitor in monitors],
        total=len(monitors),
    )


@router.post(
    "/monitors",
    response_model=MonitorRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_monitor(
    payload: MonitorCreate,
    service: MonitorServiceDependency,
) -> MonitorRead:
    monitor = await service.add(payload.address)
    return MonitorRead.from_monitor(monitor)


@router.post("/monitors/{address}/enable", response_model=MonitorRead)
async def enable_monitor(
    address: str,
    service: MonitorServiceDependency,
) -> MonitorRead:
    monitor = await service.set_enabled(address, True)
    if monitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Monitor not found")
    return MonitorRead.from_monitor(monitor)


@router.delete("/monitors/{address}", response_model=MonitorRead)
async def disable_monitor(
    address: str,
    service: MonitorServiceDependency,
) -> MonitorRead:
    monitor = await service.set_enabled(address, False)
    if monitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Monitor not found")
    return MonitorRead.from_monitor(monitor)
