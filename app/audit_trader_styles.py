import asyncio
from collections import Counter

from app.core.config import get_settings
from app.infrastructure.database import create_session, engine
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.trader_style_service import TraderStyleService


async def run() -> None:
    settings = get_settings()
    session = await create_session()
    try:
        styles = TraderStyleService(
            session,
            min_history_trades=settings.alpha_trader_min_history_trades,
            min_hold_minutes=settings.alpha_trader_min_hold_minutes,
            max_distinct_tokens_60s=(
                settings.alpha_trader_max_distinct_tokens_60s
            ),
            max_side_switches_per_token=(
                settings.alpha_trader_max_side_switches_per_token
            ),
            rapid_round_trip_seconds=(
                settings.alpha_trader_rapid_round_trip_seconds
            ),
            max_rapid_round_trips=(
                settings.alpha_trader_max_rapid_round_trips
            ),
        )
        monitors = MonitorRepository(session)
        scores = ScoreSnapshotRepository(session)
        existing = await monitors.list_all()
        rejected: Counter[str] = Counter()
        enabled_count = 0
        for monitor in existing:
            profile = await styles.evaluate(monitor.wallet.address)
            score = await scores.get_by_wallet_id(monitor.wallet_id)
            should_enable = bool(
                profile.eligible
                and score is not None
                and score.score >= settings.auto_promote_wallet_score
                and score.grade in {"A", "B"}
            )
            if should_enable:
                if not monitor.enabled:
                    monitor.last_error = None
                    await monitors.set_enabled(monitor, True)
                enabled_count += 1
                continue
            if not monitor.enabled:
                continue
            reason = profile.reason or "score_below_threshold"
            monitor.last_error = f"Trader eligibility rejected: {reason}"
            await monitors.set_enabled(monitor, False)
            rejected[reason] += 1
        print("Existing monitors examined:", len(existing))
        print("Eligible monitors enabled:", enabled_count)
        print("Ineligible monitors disabled:", sum(rejected.values()))
        for reason, count in sorted(rejected.items()):
            print(f"  {reason}: {count}")
    finally:
        await session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
