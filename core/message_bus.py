# core/message_bus.py
from __future__ import annotations
import asyncio, collections, time
from typing import Callable, Coroutine, List
from core.message import Message


class MessageBus:
    def __init__(self, substation_id: str):
        self.substation_id = substation_id
        self._subscribers: List[Callable] = []
        self._history: collections.deque = collections.deque(maxlen=600)
        self._message_count = 0
        self._rate_window: collections.deque = collections.deque(maxlen=100)

    def subscribe(self, callback):
        self._subscribers.append(callback)

    async def publish(self, msg: Message):
        self._history.append(msg)
        self._message_count += 1
        self._rate_window.append(time.time())
        await asyncio.gather(*[cb(msg) for cb in self._subscribers],
                             return_exceptions=True)

    def get_recent(self, n: int = 60) -> List[Message]:
        return list(self._history)[-n:]

    def messages_per_second(self) -> float:
        now = time.time()
        recent = [t for t in self._rate_window if now - t <= 1.0]
        return float(len(recent))

    @property
    def total_messages(self) -> int:
        return self._message_count


class InterSubstationBus:
    """Bridges Coordination Agents between Substation A and B."""
    def __init__(self):
        self._subscribers: List[Callable] = []
        self._history: collections.deque = collections.deque(maxlen=200)

    def subscribe(self, callback):
        self._subscribers.append(callback)

    async def publish(self, msg: Message):
        self._history.append(msg)
        await asyncio.gather(*[cb(msg) for cb in self._subscribers],
                             return_exceptions=True)

    def get_recent(self, n: int = 40) -> List[Message]:
        return list(self._history)[-n:]
