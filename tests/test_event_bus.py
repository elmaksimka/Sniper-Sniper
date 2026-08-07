import asyncio

import pytest

from app.core.event_bus import EventBus
from app.core.events import WalletUpdated


@pytest.mark.asyncio
async def test_handlers_run_sequentially_in_subscription_order() -> None:
    bus = EventBus()
    order: list[str] = []
    active = 0
    maximum_active = 0

    async def first(event: WalletUpdated) -> None:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        order.append("first-start")
        await asyncio.sleep(0)
        order.append("first-end")
        active -= 1

    async def second(event: WalletUpdated) -> None:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        order.append("second")
        active -= 1

    bus.subscribe(WalletUpdated, first)
    bus.subscribe(WalletUpdated, second)

    await bus.publish(WalletUpdated(wallet="wallet"))

    assert maximum_active == 1
    assert order == ["first-start", "first-end", "second"]
