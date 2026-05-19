# agents/base_agent.py
from __future__ import annotations
import asyncio, time
from abc import ABC, abstractmethod
from core.message import Message, MessageType, Priority
from core.message_bus import MessageBus
from core.vector_clock import VectorClock
from config import AGENT_TICK_SECONDS


class BaseAgent(ABC):
    def __init__(self, agent_id: str, substation: str,
                 bus: MessageBus, physics):
        self.agent_id   = agent_id
        self.substation = substation
        self.bus        = bus
        self.physics    = physics
        self.vc         = VectorClock(agent_id)
        self.running    = False
        self.tick_count = 0
        self.health     = 1.0
        self._inbox: list = []
        self.last_llm_reason: str = ""
        bus.subscribe(self._receive)

    async def _receive(self, msg: Message):
        if (msg.receiver in (self.agent_id, "BROADCAST")
                and msg.sender != self.agent_id):
            self.vc.update(msg.vector_clock)
            self._inbox.append(msg)

    async def send(self, receiver: str, msg_type: MessageType,
                   payload: dict, priority: Priority = Priority.MEDIUM,
                   llm_reason: str = ""):
        msg = Message(
            sender=self.agent_id, receiver=receiver,
            msg_type=msg_type, substation=self.substation,
            payload=payload, priority=priority,
            vector_clock=self.vc.tick(),
            llm_reason=llm_reason,
        )
        await self.bus.publish(msg)

    async def broadcast(self, msg_type: MessageType, payload: dict,
                        priority: Priority = Priority.MEDIUM,
                        llm_reason: str = ""):
        await self.send("BROADCAST", msg_type, payload, priority, llm_reason)

    async def run(self):
        self.running = True
        while self.running:
            try:
                await self.tick()
                self.tick_count += 1
            except Exception:
                pass
            await asyncio.sleep(AGENT_TICK_SECONDS)

    @abstractmethod
    async def tick(self): ...

    def status_dict(self) -> dict:
        return {
            "agent_id":   self.agent_id,
            "substation": self.substation,
            "health":     round(self.health, 2),
            "ticks":      self.tick_count,
            "last_reason": self.last_llm_reason,
        }
