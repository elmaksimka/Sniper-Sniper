import asyncio

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.notifications.telegram import TelegramNotifier


async def run() -> None:
    settings = get_settings()
    notifier = TelegramNotifier(
        settings.telegram_bot_token,
        settings.telegram_recipients,
    )
    if not notifier.enabled:
        raise RuntimeError("Telegram is not configured")

    results = await notifier.send_text(
        "✅ Alpha Engine Telegram delivery is connected.\n\n"
        "Real messages will be sent only when a top trader buys a top token."
    )
    failed = [recipient for recipient, delivered in results.items() if not delivered]
    if failed:
        raise RuntimeError(f"Telegram test failed for {len(failed)} recipient(s)")


def main() -> None:
    setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
