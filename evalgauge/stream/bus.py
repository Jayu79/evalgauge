"""A minimal publish/subscribe transport.

The point of this file is the *interface*, not the implementation. Producers publish;
consumers subscribe; neither knows who the other is. That decoupling is the whole reason
streaming systems scale — the detector doesn't care whether prompts come from a replayed
file today or real Pub/Sub tomorrow. Swap InMemoryBus for a Pub/Sub-backed bus with the
same two methods and nothing else in the pipeline changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .event import Event

Subscriber = Callable[[Event], None]


class Bus(Protocol):
    """The contract every transport must honor. Depend on this, not on a concrete bus."""

    def subscribe(self, fn: Subscriber) -> None: ...
    def publish(self, event: Event) -> None: ...


class InMemoryBus:
    """Synchronous, in-process implementation. Publishing fans out to every subscriber.

    Real Pub/Sub is asynchronous and durable; this is neither. But it honors the same
    Bus contract, which is all the producer and consumer are allowed to depend on — so
    it is a faithful stand-in for teaching and local runs.
    """

    def __init__(self) -> None:
        self._subs: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def publish(self, event: Event) -> None:
        for fn in self._subs:
            fn(event)
