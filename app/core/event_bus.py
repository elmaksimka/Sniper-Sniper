from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.events import Event

T = TypeVar("T", bound=Event)

EventHandler = Callable[[T], Awaitable[None]]


class EventBus:
    """
    Simple in-memory async event bus.

    The goal is NOT performance.

    The goal is decoupling.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[T],
        handler: EventHandler[T],
    ) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(type(event), [])

        if not handlers:
            return

        await asyncio.gather(
            *(handler(event) for handler in handlers)
        )