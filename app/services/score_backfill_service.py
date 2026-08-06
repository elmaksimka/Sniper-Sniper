from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.wallet_repository import WalletRepository
from app.services.score_snapshot_service import ScoreSnapshotService
from app.services.scoring_service import ScoringService


class ScoreBackfillService:
    def __init__(self, session: AsyncSession) -> None:
        self.wallets = WalletRepository(session)
        self.scoring = ScoringService(session)
        self.snapshots = ScoreSnapshotService(session)

    async def run(self, batch_size: int = 100) -> int:
        processed = 0
        offset = 0

        while True:
            wallets = await self.wallets.list_all(batch_size, offset)
            if not wallets:
                break

            for wallet in wallets:
                score = await self.scoring.score_wallet(wallet.address)
                if score is None:
                    continue

                await self.snapshots.save(wallet.id, score)
                processed += 1

            offset += len(wallets)
            if len(wallets) < batch_size:
                break

        return processed
