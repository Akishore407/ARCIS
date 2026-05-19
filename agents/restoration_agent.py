# agents/restoration_agent.py
from __future__ import annotations
import time
from agents.base_agent import BaseAgent
from core.message import MessageType, Priority
from core.groq_client import llm_reason, RESTORATION_SYSTEM

STEPS = [
    ("ISOLATE",   "Isolating faulted section from healthy bus"),
    ("ASSESS",    "Assessing healthy sections via voltage scan"),
    ("ENERGIZE",  "Energizing alternate supply path"),
    ("RECONNECT", "Reconnecting loads in priority order"),
    ("VERIFY",    "Verifying stable voltage and current profiles"),
]


class RestorationAgent(BaseAgent):
    def __init__(self, agent_id, substation, bus, physics):
        super().__init__(agent_id, substation, bus, physics)
        self.restorations_completed = 0
        self._sequence: list = []
        self._next_step_time: float = 0
        self._target_breaker: str | None = None

    async def tick(self):
        for msg in list(self._inbox):
            self._inbox.remove(msg)
            if msg.msg_type == MessageType.RESTORATION:
                event   = msg.payload.get("event", "")
                breaker = msg.payload.get("breaker", "")
                if event == "BREAKER_TRIPPED" and not self._sequence:
                    self._start(breaker)

        now = time.time()
        if self._sequence and now >= self._next_step_time:
            code, desc = self._sequence.pop(0)
            reason = await llm_reason(
                RESTORATION_SYSTEM,
                f"Executing restoration step {code}: {desc}. "
                f"Breaker={self._target_breaker}, "
                f"substation={self.substation}. Why is this step safe?",
                fallback=f"Restoration step {code}: {desc}"
            )
            self.last_llm_reason = reason
            await self.broadcast(MessageType.RESTORATION, {
                "step": code, "description": desc,
                "breaker": self._target_breaker,
            }, Priority.HIGH, reason)

            if code == "VERIFY":
                self._finish()
                self.restorations_completed += 1
                await self.broadcast(MessageType.STATUS, {
                    "event": "RESTORATION_COMPLETE",
                    "breaker": self._target_breaker,
                    "message": f"Substation {self.substation} fully restored",
                }, Priority.HIGH)
                self._target_breaker = None
            self._next_step_time = now + 4.0

        await self.broadcast(MessageType.STATUS, {
            "agent": self.agent_id,
            "restoring": bool(self._sequence),
            "steps_remaining": len(self._sequence),
            "restorations_completed": self.restorations_completed,
        }, Priority.LOW)

        self.health = 0.5 if self._sequence else 1.0

    def _start(self, breaker: str):
        self._target_breaker = breaker
        self._sequence = list(STEPS)
        self._next_step_time = time.time() + 2.0

    def _finish(self):
        for b in self.physics.breakers:
            if b.name == self._target_breaker:
                b.close()
        for tr in self.physics.transformers:
            if tr.tripped:
                tr.reset_trip()
                tr.load_pct = 0.28

    def status_dict(self):
        d = super().status_dict()
        d.update({"restorations_completed": self.restorations_completed,
                  "restoring": bool(self._sequence)})
        return d
