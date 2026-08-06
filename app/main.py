import asyncio

from app.bootstrap.container import Container
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import create_session, engine


async def run() -> None:
    session = await create_session()

    try:
        container = Container(
            session=session,
        )

        container.setup()

        print(
            "Starting token detection..."
        )

        await container.token_detection_service.scan_wallet(
            wallet=(
                "So11111111111111111111111111111111111111112"
            ),
            limit=5,
        )

    finally:
        await session.close()
        await engine.dispose()


def main() -> None:
    setup_logging()

    logger = get_logger(
        "alpha-engine",
    )

    logger.info(
        "application_started",
        message="Alpha Engine is running",
    )

    asyncio.run(run())


if __name__ == "__main__":
    main()