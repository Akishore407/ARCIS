# prediction/failure_predictor.py
from __future__ import annotations
import time
from typing import Dict, List
from detectors.all_detectors import DetectionResult


class FailurePredictor:
    CLASSES = ["Oscillation","CascadeStarvation","Contradiction",
               "SemanticDrift","Collusion","RaceCondition"]

    def __init__(self):
        self._history: Dict[str, list] = {c: [] for c in self.CLASSES}
        self._predictions: Dict[str, dict] = {}

    def update(self, results: List[DetectionResult]):
        now = time.time()
        for r in results:
            fc = r.failure_class
            if fc not in self._history: continue
            self._history[fc].append((now, r.confidence, r.detected))
            if len(self._history[fc]) > 25:
                self._history[fc].pop(0)
        for fc in self.CLASSES:
            self._predictions[fc] = self._predict(fc)

    def _predict(self, fc: str) -> dict:
        hist = self._history[fc]
        if not hist:
            return {"ttf_seconds": None, "trend": 0.0,
                    "risk_level": "NONE", "current_confidence": 0.0}
        confs = [c for _, c, _ in hist]
        times = [t for t, _, _ in hist]
        cur   = confs[-1]

        # Linear trend
        trend = 0.0
        if len(confs) >= 4:
            n     = len(confs)
            t_rel = [t - times[0] for t in times]
            mt    = sum(t_rel) / n
            mc    = sum(confs)  / n
            num   = sum((t_rel[i]-mt)*(confs[i]-mc) for i in range(n))
            den   = sum((t_rel[i]-mt)**2 for i in range(n))
            trend = num / den if den > 0 else 0.0

        ttf = (1.0 - cur) / trend if trend > 0 and cur < 1.0 else None
        risk = ("CRITICAL" if cur >= 0.80 else
                "HIGH"     if cur >= 0.55 else
                "MEDIUM"   if cur >= 0.30 else
                "LOW"      if cur >= 0.10 else "NONE")
        return {
            "ttf_seconds":         round(ttf, 1) if ttf else None,
            "trend":               round(trend, 5),
            "risk_level":          risk,
            "current_confidence":  round(cur, 3),
        }

    def get_predictions(self) -> dict:
        return dict(self._predictions)
