from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.infrastructure.database import async_session_factory
from app.listeners.helius_client import HeliusClient
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.services.paper_copy_reconciliation_service import (
    PaperCopyReconciliationService,
)


async def close_positions(reason: str, *, write_off_unroutable: bool) -> tuple[int, int, int]:
    settings = get_settings()
    helius = HeliusClient()
    try:
        async with async_session_factory() as session:
            service = PaperCopyReconciliationService(
                PaperCopyRepository(session),
                helius,
                stop_loss_pct=settings.paper_copy_stop_loss_pct,
                break_even_activation_pct=(
                    settings.paper_copy_break_even_activation_pct
                ),
                trailing_activation_pct=settings.paper_copy_trailing_activation_pct,
                trailing_drawdown_pct=settings.paper_copy_trailing_drawdown_pct,
                strategy_version=settings.paper_copy_strategy_version,
            )
            return await service.close_all_positions(
                settings.paper_copy_portfolio_wallet,
                reason=reason,
                write_off_unroutable=write_off_unroutable,
            )
    finally:
        await helius.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Close every open paper-copy position")
    parser.add_argument("--reason", default="strategy reset to route-risk-v2")
    parser.add_argument("--write-off-unroutable", action="store_true")
    args = parser.parse_args()
    closed, deferred, written_off = asyncio.run(
        close_positions(
            args.reason,
            write_off_unroutable=args.write_off_unroutable,
        )
    )
    print(f"closed={closed} deferred={deferred} written_off={written_off}")


if __name__ == "__main__":
    main()
