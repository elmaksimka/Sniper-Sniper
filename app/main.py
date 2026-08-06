import asyncio

from app.bootstrap.container import Container
from app.core.events import TokenCreated
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import create_session, engine


async def run() -> None:
    session = await create_session()

    try:
        container = Container(
            session=session,
        )

        container.setup()

        await container.event_bus.publish(
            TokenCreated(
                token_address="8xDemoTokenAddress123",
                creator="DemoCreatorWallet",
            )
        )

    finally:
        await session.close()
        await engine.dispose()


def main() -> None:
    setup_logging()

    logger = get_logger(
        "alpha-engine"
    )

    logger.info(
        "application_started",
        message="Alpha Engine is running",
    )

    asyncio.run(run())


if __name__ == "__main__":
    main()