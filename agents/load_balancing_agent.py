# agents/load_balancing_agent.py
from __future__ import annotations
import networkx as nx
from agents.base_agent import BaseAgent
from core.message import MessageType, Priority
from core.groq_client import llm_reason, BALANCING_SYSTEM
from config import FEEDER_WARNING_PCT


class LoadBalancingAgent(BaseAgent):
    def __init__(self, agent_id, substation, bus, physics):
        super().__init__(agent_id, substation, bus, physics)
        self.rebalances = 0
        self._forecast_demand: float | None = None
        self._reply_cooldown = 0.0
        import time
        self._reply_cooldown = 0.0

    async def tick(self):
        import time
        now = time.time()

        for msg in list(self._inbox):
            self._inbox.remove(msg)
            if msg.msg_type == MessageType.FORECAST:
                self._forecast_demand = msg.payload.get("predicted_mw")
                # Only reply if cooldown has passed (prevents oscillation)
                if now > self._reply_cooldown:
                    self._reply_cooldown = now + 2.0
                    await self.send(msg.sender, MessageType.STATUS, {
                        "current_load": self._total_load(),
                        "capacity_margin": self._capacity_margin(),
                    }, Priority.MEDIUM)

        # Graph-based optimisation via NetworkX
        overloaded  = [f for f in self.physics.feeders
                       if f.online and f.load_pct >= FEEDER_WARNING_PCT]
        underloaded = [f for f in self.physics.feeders
                       if f.online and f.load_pct < 0.60]

        shifted_mw = 0.0
        if overloaded and underloaded:
            G = nx.DiGraph()
            for ol in overloaded:
                for ul in underloaded:
                    cap = ul.rated_mw - ul.load_mw
                    G.add_edge(ol.name, ul.name, capacity=cap)
            for ol in overloaded:
                for ul in underloaded:
                    shift = min(ol.load_mw * 0.10,
                                ul.rated_mw - ul.load_mw)
                    if shift > 0.05:
                        ol.load_mw = max(0.3, ol.load_mw - shift)
                        ul.load_mw = min(ul.rated_mw, ul.load_mw + shift)
                        shifted_mw += shift
                        self.rebalances += 1

        if shifted_mw > 0:
            reason = await llm_reason(
                BALANCING_SYSTEM,
                f"Shifted {shifted_mw:.2f}MW from overloaded feeders to "
                f"underloaded feeders. Current total load={self._total_load():.1f}MW. "
                f"Capacity margin={self._capacity_margin():.1%}. Was this effective?",
                fallback=f"Rebalanced {shifted_mw:.2f}MW across feeders"
            )
            self.last_llm_reason = reason
            await self.broadcast(MessageType.STATUS, {
                "action": "REBALANCE",
                "shifted_mw": round(shifted_mw, 2),
                "rebalances": self.rebalances,
            }, Priority.MEDIUM, reason)

        await self.broadcast(MessageType.STATUS, {
            "agent": self.agent_id,
            "feeders": [f.to_dict() for f in self.physics.feeders],
            "rebalances": self.rebalances,
            "total_load_mw": round(self._total_load(), 2),
        }, Priority.LOW)

        ol_count = len([f for f in self.physics.feeders
                        if f.load_pct >= 1.0])
        self.health = max(0.1, 1.0 - ol_count * 0.25)

    def _total_load(self) -> float:
        return sum(f.load_mw for f in self.physics.feeders if f.online)

    def _capacity_margin(self) -> float:
        cap = sum(f.rated_mw for f in self.physics.feeders if f.online)
        return (cap - self._total_load()) / cap if cap else 0

    def status_dict(self):
        d = super().status_dict()
        d.update({"rebalances": self.rebalances})
        return d
