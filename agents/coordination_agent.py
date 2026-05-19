# agents/coordination_agent.py
from __future__ import annotations
import time
from agents.base_agent import BaseAgent
from core.message import Message, MessageType, Priority
from core.message_bus import InterSubstationBus


class CoordinationAgent(BaseAgent):
    def __init__(self, agent_id, substation, bus, physics,
                 inter_bus: InterSubstationBus):
        super().__init__(agent_id, substation, bus, physics)
        self.inter_bus = inter_bus
        self.inter_bus.subscribe(self._receive_inter)
        self.coordination_msgs = 0
        self.inject_unit_mismatch = False
        self.inject_tie_overload  = False
        self._peer_load: float | None = None

    async def _receive_inter(self, msg: Message):
        if msg.sender != self.agent_id:
            self._inbox.append(msg)

    async def tick(self):
        for msg in list(self._inbox):
            self._inbox.remove(msg)
            if msg.msg_type == MessageType.COORDINATION:
                self._peer_load = msg.payload.get("load_mw")

        my_load = self.physics.total_load_mw()
        unit = "MVA" if self.inject_unit_mismatch else "MW"
        tie  = "TL-01" if self.inject_tie_overload else f"TL-{self.substation}"

        coord_msg = Message(
            sender=self.agent_id,
            receiver="BROADCAST",
            msg_type=MessageType.COORDINATION,
            substation=self.substation,
            payload={
                "load_mw": round(my_load, 2),
                "unit": unit,
                "tie_line": tie,
                "solar_gen": round(self.physics.solar_generation_mw(), 2),
                "requesting_support": my_load > 32.0,
            },
            priority=Priority.MEDIUM,
            vector_clock=self.vc.tick()
        )
        await self.inter_bus.publish(coord_msg)
        self.coordination_msgs += 1

        await self.broadcast(MessageType.COORDINATION, {
            "peer_load": self._peer_load,
            "my_load": round(my_load, 2),
            "unit": unit,
            "tie_line": tie,
        }, Priority.LOW)

        self.health = 0.45 if self.inject_unit_mismatch else 1.0

    def status_dict(self):
        d = super().status_dict()
        d.update({"coordination_msgs": self.coordination_msgs,
                  "unit_mismatch": self.inject_unit_mismatch,
                  "tie_overload": self.inject_tie_overload})
        return d
