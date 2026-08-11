from __future__ import annotations

import asyncio

from app.bootstrap.container import Container
from app.core.copy_trading import CopyTradingScoreCalculator
from app.infrastructure.database import async_session_factory, engine
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository


async def run() -> None:
    updated = 0
    async with async_session_factory() as session:
        heartbeats = HeartbeatRepository(session)
        scores = ScoreSnapshotRepository(session)
        style_service = Container(session).trader_style_service
        calculator = CopyTradingScoreCalculator()
        rows = await heartbeats.list_by_prefix("candidate:")
        for row in rows:
            if row.service_name.startswith(
                ("candidate-pair:", "candidate-source:", "candidate-discovery:")
            ):
                continue
            details = row.details if isinstance(row.details, dict) else {}
            wallet = row.service_name.removeprefix("candidate:")
            snapshot = await scores.get_by_wallet_address(wallet)
            if snapshot is None:
                continue
            style = await style_service.evaluate(wallet)
            assessment = calculator.calculate(snapshot, style)
            await heartbeats.beat(
                row.service_name,
                "copy-score-backfill",
                {
                    **details,
                    "copy_score": assessment.score,
                    "copy_mode": assessment.mode,
                },
            )
            updated += 1
    await engine.dispose()
    print(f"Updated copy scores: {updated}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
