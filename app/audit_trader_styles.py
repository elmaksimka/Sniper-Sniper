import asyncio
from collections import Counter

from app.core.config import get_settings
from app.infrastructure.database import create_session, engine
from app.repositories.monitor_repository import MonitorRepository
from app.services.trader_style_service import TraderStyleService


async def run() -> None:
    settings = get_settings()
    session = await create_session()
    try:
        styles = TraderStyleService(
            session,
            min_history_trades=settings.alpha_trader_min_history_trades,
            min_hold_minutes=settings.alpha_trader_min_hold_minutes,
            max_trades_60s=settings.alpha_trader_max_trades_60s,
            max_trades_per_token=settings.alpha_trader_max_trades_per_token,
            rapid_round_trip_seconds=(
                settings.alpha_trader_rapid_round_trip_seconds
            ),
            max_rapid_round_trips=(
                settings.alpha_trader_max_rapid_round_trips
            ),
        )
        monitors = MonitorRepository(session)
        enabled = await monitors.list_all(enabled_only=True)
        rejected: Counter[str] = Counter()
        for monitor in enabled:
            profile = await styles.evaluate(monitor.wallet.address)
            if profile.eligible:
                continue
            monitor.last_error = f"Trader style rejected: {profile.reason}"
            await monitors.set_enabled(monitor, False)
            rejected[profile.reason or "unknown"] += 1
        print("Enabled monitors examined:", len(enabled))
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
