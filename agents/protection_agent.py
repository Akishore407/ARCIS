# agents/protection_agent.py
from __future__ import annotations
import time
from agents.base_agent import BaseAgent
from core.message import MessageType, Priority
from core.groq_client import llm_reason, PROTECTION_SYSTEM
from config import RELAY_TRIP_DELAY_SEC


class ProtectionAgent(BaseAgent):
    def __init__(self, agent_id, substation, bus, physics):
        super().__init__(agent_id, substation, bus, physics)
        self.trips_executed   = 0
        self.closes_executed  = 0
        self._pending_trips: dict = {}
        self.override_active  = False

    async def tick(self):
        for msg in list(self._inbox):
            self._inbox.remove(msg)
            if msg.msg_type == MessageType.ALERT:
                await self._handle_alert(msg)

        now = time.time()
        to_trip = [n for n, t in self._pending_trips.items() if now >= t]
        for name in to_trip:
            del self._pending_trips[name]
            if self.override_active:
                await self.broadcast(MessageType.STATUS, {
                    "info": f"Trip {name} suppressed by ARCIS command lock"
                }, Priority.HIGH)
                continue
            await self._execute_trip(name)

        await self.broadcast(MessageType.STATUS, {
            "agent": self.agent_id,
            "breakers": [b.to_dict() for b in self.physics.breakers],
            "trips_executed": self.trips_executed,
            "override_active": self.override_active,
        }, Priority.LOW)

        tripped = sum(1 for b in self.physics.breakers if not b.closed)
        self.health = max(0.1, 1.0 - tripped * 0.12)

    async def _handle_alert(self, msg):
        payload  = msg.payload
        severity = payload.get("severity", "")
        tr_name  = payload.get("transformer", "")
        if severity in ("CRITICAL", "TRIP") and tr_name:
            breaker = self._find_breaker(tr_name)
            if breaker and breaker.closed and breaker.name not in self._pending_trips:
                self._pending_trips[breaker.name] = time.time() + RELAY_TRIP_DELAY_SEC
                reason = await llm_reason(
                    PROTECTION_SYSTEM,
                    f"Received {severity} alert for {tr_name} at temperature "
                    f"{payload.get('temperature',0)}°C. Should I trip {breaker.name}?",
                    fallback=f"Scheduling trip on {breaker.name} due to {severity} on {tr_name}"
                )
                self.last_llm_reason = reason
                await self.broadcast(MessageType.COMMAND, {
                    "action": "PENDING_TRIP",
                    "breaker": breaker.name,
                    "reason": tr_name,
                    "trip_in_sec": RELAY_TRIP_DELAY_SEC,
                }, Priority.CRITICAL, reason)

    async def _execute_trip(self, breaker_name: str):
        for b in self.physics.breakers:
            if b.name == breaker_name:
                b.trip()
                self.trips_executed += 1
                await self.broadcast(MessageType.COMMAND, {
                    "action": "BREAKER_TRIP",
                    "breaker": breaker_name,
                    "message": f"CB {breaker_name} opened — relay protection",
                }, Priority.CRITICAL)
                await self.send("RestorationAgent", MessageType.RESTORATION, {
                    "event": "BREAKER_TRIPPED",
                    "breaker": breaker_name,
                }, Priority.HIGH)
                break

    def _find_breaker(self, tr_name: str):
        mapping = {"T1":0,"T2":1,"T3":2,"T4":3,"T5":4,
                   "T6":0,"T7":1,"T8":2,"T9":3,"T10":4}
        idx = mapping.get(tr_name, -1)
        if 0 <= idx < len(self.physics.breakers):
            return self.physics.breakers[idx]
        return None

    def status_dict(self):
        d = super().status_dict()
        d.update({"trips_executed": self.trips_executed,
                  "override_active": self.override_active})
        return d
