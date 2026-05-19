# core/arcis.py
from __future__ import annotations
import asyncio, time
from typing import Dict, List
from core.message import Message
from core.message_bus import MessageBus, InterSubstationBus
from core.interaction_graph import InteractionGraph
from detectors.all_detectors import (
    OscillationDetector, CascadeDetector, ConflictDetector,
    SemanticDriftDetector, CollusionDetector, RaceConditionDetector,
    DetectionResult
)
from prediction.failure_predictor import FailurePredictor
from intervention.intervention_engine import InterventionEngine
from config import ARCIS_TICK_SECONDS


class ARCISMetaLayer:
    def __init__(self, substations: Dict[str, dict],
                 inter_bus: InterSubstationBus):
        self.substations = substations
        self.inter_bus   = inter_bus
        self.injector    = None

        self.graphs: Dict[str, InteractionGraph] = {
            sid: InteractionGraph(sid) for sid in substations
        }
        self.graphs["INTER"] = InteractionGraph("INTER")

        self._messages: Dict[str, List[Message]] = {sid: [] for sid in substations}
        self._inter_messages: List[Message] = []

        for sid, sub in substations.items():
            bus: MessageBus = sub["bus"]
            def make_cb(substation_id):
                async def _cb(msg: Message):
                    self.graphs[substation_id].record(msg.sender, msg.receiver)
                    self._messages[substation_id].append(msg)
                    if len(self._messages[substation_id]) > 600:
                        self._messages[substation_id].pop(0)
                return _cb
            bus.subscribe(make_cb(sid))

        async def _inter_cb(msg: Message):
            self.graphs["INTER"].record(msg.sender, msg.receiver)
            self._inter_messages.append(msg)
            if len(self._inter_messages) > 200:
                self._inter_messages.pop(0)
        inter_bus.subscribe(_inter_cb)

        self.detectors = [
            OscillationDetector(),
            CascadeDetector(),
            ConflictDetector(),
            SemanticDriftDetector(),
            CollusionDetector(),
            RaceConditionDetector(),
        ]
        self.predictor  = FailurePredictor()
        self.intervener = InterventionEngine()

        self.latest_results: List[DetectionResult] = []
        self.latest_interventions: List[dict] = []
        self.tick_count = 0
        self.running    = False

    async def run(self):
        self.running = True
        while self.running:
            await asyncio.sleep(ARCIS_TICK_SECONDS)
            try:
                await self._scan()
                self.tick_count += 1
            except Exception:
                pass

    async def _scan(self):
        flags = self.injector.active_flags()      if self.injector else {}
        env   = self.injector.get_active_condition() if self.injector else {}
        env   = env or {}

        sid   = list(self.substations.keys())[0]
        graph = self.graphs[sid]
        msgs  = list(self._messages[sid])

        results = [d.detect(graph, msgs, flags, env) for d in self.detectors]

        self.latest_results       = results
        self.predictor.update(results)
        self.latest_interventions = self.intervener.evaluate(
            results, self.substations
        )

    def snapshot(self) -> dict:
        env = self.injector.get_active_condition() if self.injector else None
        return {
            "tick":          self.tick_count,
            "detections":    [r.to_dict() for r in self.latest_results],
            "predictions":   self.predictor.get_predictions(),
            "interventions": self.intervener.recent_interventions(10),
            "environment":   env,
            "graphs": {
                sid: {"nodes": g.get_node_data(), "edges": g.get_edge_data()}
                for sid, g in self.graphs.items()
            },
        }
