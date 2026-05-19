# core/interaction_graph.py
from __future__ import annotations
import time, collections
from typing import Dict, List, Tuple
import networkx as nx


class InteractionGraph:
    DECAY_HALF_LIFE = 25.0

    def __init__(self, substation_id: str):
        self.substation_id = substation_id
        self.graph = nx.DiGraph()
        self._events: collections.deque = collections.deque(maxlen=2000)

    def record(self, sender: str, receiver: str):
        now = time.time()
        self._events.append((sender, receiver, now))
        for n in (sender, receiver):
            if not self.graph.has_node(n):
                self.graph.add_node(n, substation=self.substation_id)
        if self.graph.has_edge(sender, receiver):
            self.graph[sender][receiver]["count"] += 1
            self.graph[sender][receiver]["last_seen"] = now
        else:
            self.graph.add_edge(sender, receiver, count=1, weight=0.0, last_seen=now)

    def refresh_weights(self):
        now = time.time()
        window = 25.0
        cutoff = now - window
        counts: Dict[Tuple, int] = collections.defaultdict(int)
        for s, r, ts in self._events:
            if ts >= cutoff:
                counts[(s, r)] += 1
        mx = max(counts.values(), default=1)
        for (s, d), cnt in counts.items():
            if self.graph.has_edge(s, d):
                w = cnt / mx
                age = now - self.graph[s][d].get("last_seen", now)
                decay = 0.5 ** (age / self.DECAY_HALF_LIFE)
                self.graph[s][d]["weight"] = round(w * decay, 4)

    def get_edge_data(self) -> List[dict]:
        self.refresh_weights()
        return [{"source": s, "target": d,
                 "weight": data.get("weight", 0),
                 "count":  data.get("count", 0)}
                for s, d, data in self.graph.edges(data=True)]

    def get_node_data(self) -> List[dict]:
        return [{"id": n, "substation": data.get("substation", "")}
                for n, data in self.graph.nodes(data=True)]

    def strongly_connected_components(self) -> List[List[str]]:
        return [list(s) for s in nx.strongly_connected_components(self.graph)
                if len(s) > 1]

    def message_rate(self, sender: str, window: float = 5.0) -> float:
        now = time.time()
        cutoff = now - window
        count = sum(1 for s, _, ts in self._events
                    if s == sender and ts >= cutoff)
        return count / window
