from app.core.logging import get_logger, setup_logging


def main() -> None:
    setup_logging()

    logger = get_logger("alpha-engine")

    logger.info(
        "application_started",
        message="Alpha Engine is running",
    )


if __name__ == "__main__":
    main()