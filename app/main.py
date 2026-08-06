import asyncio

from sqlalchemy import text

from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import engine


async def check_database() -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT 1")
        )

        print(
            "Database response:",
            result.scalar(),
        )


def main() -> None:
    setup_logging()

    logger = get_logger("alpha-engine")

    logger.info(
        "application_started",
        message="Alpha Engine is running",
    )

    asyncio.run(check_database())


if __name__ == "__main__":
    main()