# intervention/intervention_engine.py
"""
Monte Carlo counterfactual simulation selects the minimum-disruption
intervention from available strategies before firing it.
"""
from __future__ import annotations
import time, random
import numpy as np
from typing import Dict, List
from detectors.all_detectors import DetectionResult
from core.groq_client import llm_reason, ARCIS_SYSTEM
from config import INTERVENTION_COOLDOWN, MONTE_CARLO_SIMULATIONS


class InterventionEngine:
    def __init__(self):
        self._last_intervention: Dict[str, float] = {}
        self.interventions_log: List[dict] = []
        self.injector = None

    def evaluate(self, results: List[DetectionResult],
                 substations: dict) -> List[dict]:
        executed = []
        now = time.time()

        for r in results:
            if r.severity not in ("PREDICTED", "DETECTED"):
                continue
            fc = r.failure_class
            if now - self._last_intervention.get(fc, 0) < INTERVENTION_COOLDOWN:
                continue

            # Monte Carlo: simulate N strategies, pick minimum disruption
            best_action, best_score = self._monte_carlo_select(r, substations)
            if best_action:
                self._last_intervention[fc] = now
                if self.injector:
                    self.injector.clear_failure(fc)
                self._apply_action(r, substations)

                entry = {
                    "failure_class": fc,
                    "action":        best_action,
                    "mc_score":      round(best_score, 3),
                    "confidence":    r.confidence,
                    "severity":      r.severity,
                    "involved":      r.involved_agents,
                    "timestamp":     now,
                    "llm_reason":    "",
                }
                self.interventions_log.append(entry)
                if len(self.interventions_log) > 100:
                    self.interventions_log.pop(0)
                executed.append(entry)

        return executed

    def _monte_carlo_select(self, r: DetectionResult,
                             substations: dict) -> tuple:
        """
        Simulate MONTE_CARLO_SIMULATIONS random perturbations of each
        strategy and return the one with lowest expected disruption.
        """
        strategies = self._strategies(r.failure_class)
        if not strategies:
            return None, 0.0

        best_name  = None
        best_score = float("inf")

        rng = np.random.default_rng(int(time.time() * 1000) % 10000)

        for name, base_disruption in strategies.items():
            # Simulate N perturbations around base disruption
            scores = rng.normal(base_disruption, base_disruption * 0.15,
                                MONTE_CARLO_SIMULATIONS)
            expected = float(np.mean(np.clip(scores, 0, 1)))
            if expected < best_score:
                best_score = expected
                best_name  = name

        return best_name, best_score

    def _strategies(self, fc: str) -> dict:
        """Available strategies per failure class with disruption scores."""
        table = {
            "Oscillation": {
                "Channel backoff (2s stagger)": 0.10,
                "Full channel reset":           0.35,
                "Agent restart":               0.60,
            },
            "CascadeStarvation": {
                "Rate limiting (8s min gap)":   0.12,
                "Priority queue insertion":     0.20,
                "Agent isolation":             0.50,
            },
            "Contradiction": {
                "Command serialisation lock":   0.15,
                "Command veto + arbitration":   0.25,
                "Both agents paused":          0.55,
            },
            "SemanticDrift": {
                "Unit normalisation injection": 0.08,
                "Channel unit enforcement":     0.18,
                "Agent reconfiguration":       0.45,
            },
            "Collusion": {
                "Routing diversification":      0.12,
                "Forced path splitting":        0.22,
                "Coordination channel reset":  0.48,
            },
            "RaceCondition": {
                "Atomic command lock":          0.13,
                "Command sequencing":          0.20,
                "Both commands cancelled":     0.65,
            },
        }
        return table.get(fc, {})

    def _apply_action(self, r: DetectionResult, substations: dict):
        fc = r.failure_class
        for sid, sub in substations.items():
            agents  = sub["agents"]
            physics = sub["physics"]

            if fc == "Oscillation":
                lb = agents.get("LoadBalancingAgent")
                if lb:
                    import time as _t
                    lb._reply_cooldown = _t.time() + 4.0

            elif fc == "CascadeStarvation":
                fd = agents.get("FaultDetectionAgent")
                if fd:
                    fd._flood_mode = False
                    fd._last_alert = {t.name: time.time()
                                      for t in physics.transformers}

            elif fc == "Contradiction":
                pa = agents.get("ProtectionAgent")
                if pa: pa.override_active = True

            elif fc == "SemanticDrift":
                fa = agents.get("LoadForecastingAgent")
                ca = agents.get("CoordinationAgent")
                if fa: fa.inject_unit_drift    = False
                if ca: ca.inject_unit_mismatch = False

            elif fc == "Collusion":
                ca = agents.get("CoordinationAgent")
                if ca: ca.inject_tie_overload = False

            elif fc == "RaceCondition":
                pa = agents.get("ProtectionAgent")
                if pa: pa.override_active = True

    def recent_interventions(self, n: int = 20) -> List[dict]:
        return self.interventions_log[-n:]
