import asyncio
import sys

from app.core.config import get_settings
from app.infrastructure.database import async_session_factory, engine
from app.notifications.telegram import TelegramNotifier
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.services.candidate_audit_progress_service import (
    CandidateAuditProgressService,
)


async def run(*, print_only: bool = False) -> None:
    settings = get_settings()
    notifier = TelegramNotifier(
        settings.telegram_bot_token,
        settings.telegram_recipients,
    )
    if not notifier.enabled:
        raise RuntimeError("Telegram is not configured")

    async with async_session_factory() as session:
        pairs = await CandidateAuditProgressService(
            HeartbeatRepository(session)
        ).get(settings.candidate_enrichment_maximum_history_transactions)

    messages = notifier._candidate_audit_progress_messages(
        {"candidate_audit_pairs": pairs}
    )
    if not messages:
        messages = ("DexScreener audit queue is empty.",)

    if print_only:
        print("\n\n".join(messages))
        await engine.dispose()
        return

    failed: set[str] = set()
    for message in messages:
        results = await notifier.send_text(message)
        failed.update(
            recipient for recipient, delivered in results.items() if not delivered
        )
    await engine.dispose()
    if failed:
        raise RuntimeError(
            f"Telegram progress delivery failed for {len(failed)} recipient(s)"
        )


def main() -> None:
    asyncio.run(run(print_only="--print-only" in sys.argv[1:]))


if __name__ == "__main__":
    main()
