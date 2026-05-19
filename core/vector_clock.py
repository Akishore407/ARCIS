# core/vector_clock.py
from __future__ import annotations
from typing import Dict


class VectorClock:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._clock: Dict[str, int] = {agent_id: 0}

    def tick(self) -> Dict[str, int]:
        self._clock[self.agent_id] = self._clock.get(self.agent_id, 0) + 1
        return dict(self._clock)

    def update(self, received: Dict[str, int]):
        for agent, ts in received.items():
            self._clock[agent] = max(self._clock.get(agent, 0), ts)
        self._clock[self.agent_id] = self._clock.get(self.agent_id, 0) + 1

    def concurrent(self, vc_a: Dict[str, int], vc_b: Dict[str, int]) -> bool:
        all_a = set(vc_a) | set(vc_b)
        ab = all(vc_a.get(a, 0) <= vc_b.get(a, 0) for a in all_a)
        ba = all(vc_b.get(a, 0) <= vc_a.get(a, 0) for a in all_a)
        return not ab and not ba

    @property
    def value(self) -> Dict[str, int]:
        return dict(self._clock)
