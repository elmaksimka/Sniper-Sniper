import asyncio
from collections.abc import Iterable
from typing import Any

from app.infrastructure.database import async_session_factory, engine
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.score_snapshot_service import ScoreSnapshotService
from app.services.scoring_service import ScoringService


def ranking_addresses(rows: Iterable[object]) -> tuple[str, ...]:
    addresses: set[str] = set()
    for row in rows:
        details = getattr(row, "details", None)
        if not isinstance(details, dict):
            continue
        traders = details.get("traders")
        if not isinstance(traders, list):
            continue
        for trader in traders:
            if not isinstance(trader, dict):
                continue
            address = str(trader.get("wallet") or "").strip()
            if address:
                addresses.add(address)
    return tuple(sorted(addresses))


async def run() -> None:
    async with async_session_factory() as session:
        heartbeats = HeartbeatRepository(session)
        rows = await heartbeats.list_by_prefix("candidate-pair:", limit=5_000)
        addresses = ranking_addresses(rows)
        wallets = WalletRepository(session)
        scoring = ScoringService(session)
        snapshots = ScoreSnapshotService(session)
        updated: list[dict[str, Any]] = []

        for address in addresses:
            wallet = await wallets.get_by_address(address)
            if wallet is None:
                continue
            score = await scoring.score_wallet(address)
            if score is None:
                continue
            await snapshots.save(wallet.id, score)
            audit = await heartbeats.get(f"candidate:{address}")
            if audit is not None and isinstance(audit.details, dict):
                audit.details = {**audit.details, "score_after": score.score}
                await session.commit()
            updated.append(
                {
                    "wallet": address,
                    "score": score.score,
                    "win_rate": score.win_rate,
                    "pnl_concentration": score.pnl_concentration_ratio,
                    "roi_ex_top": score.realized_roi_ex_top_position,
                }
            )

    await engine.dispose()
    print({"ranking_wallets_updated": len(updated), "wallets": updated})


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
