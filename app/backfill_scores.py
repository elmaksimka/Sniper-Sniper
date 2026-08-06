import asyncio

from app.infrastructure.database import create_session, engine
from app.services.score_backfill_service import ScoreBackfillService


async def run() -> None:
    session = await create_session()
    try:
        processed = await ScoreBackfillService(session).run()
        print("Wallet score snapshots updated:", processed)
    finally:
        await session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
