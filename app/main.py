import asyncio

from app.bootstrap.container import Container
from app.infrastructure.database import create_session, engine


WALLET = "AUaPMKd13d633cXRRrPRfTeL5XRN64ngDWLEfH5zfBML"


async def run() -> None:
    session = await create_session()

    try:
        container = Container(session)
        container.setup()
        await container.token_detection_service.scan_wallet(WALLET)
    finally:
        await session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
