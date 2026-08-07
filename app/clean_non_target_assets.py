import asyncio

from app.infrastructure.database import create_session, engine
from app.services.non_target_cleanup_service import NonTargetCleanupService


async def run() -> None:
    session = await create_session()
    try:
        result = await NonTargetCleanupService(session).run()
        print("Non-target trade rows deleted:", result.trades_deleted)
        print("Non-target token rows deleted:", result.tokens_deleted)
        print("Wallet score snapshots updated:", result.wallet_scores_updated)
        print("Token score snapshots updated:", result.token_scores_updated)
        print("Ineligible monitors disabled:", result.monitors_disabled)
    finally:
        await session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
