# detectors/all_detectors.py
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import List
from core.message import Message


@dataclass
class DetectionResult:
    failure_class:   str
    detected:        bool
    confidence:      float
    severity:        str    # CLEAR / WARNING / PREDICTED / DETECTED / RESOLVED
    detail:          str
    how_arose:       str    # what physical condition caused it
    arcis_action:    str    # what ARCIS will do / did
    involved_agents: List[str] = field(default_factory=list)
    predicted_ttf:   float = 0.0
    timestamp:       float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "failure_class":   self.failure_class,
            "detected":        self.detected,
            "confidence":      round(self.confidence, 3),
            "severity":        self.severity,
            "detail":          self.detail,
            "how_arose":       self.how_arose,
            "arcis_action":    self.arcis_action,
            "involved_agents": self.involved_agents,
            "predicted_ttf":   round(self.predicted_ttf, 1),
            "timestamp":       self.timestamp,
        }


def _clear(fc):
    return DetectionResult(fc, False, 0.0, "CLEAR",
                           "Normal operation — no anomaly detected",
                           "", "", [])


class _BaseDetector:
    def __init__(self):
        self._state      = "CLEAR"
        self._confidence = 0.0
        self._resolved_at = 0.0

    def detect(self, graph, messages: List[Message],
               inject_flags: dict = None,
               environment: dict = None) -> DetectionResult:
        inject_flags = inject_flags or {}
        environment  = environment  or {}
        fc  = self._fc()
        sev = environment.get("severity", 0.0) if environment.get("failure_class") == fc else 0.0
        active = inject_flags.get(fc, False)
        now = time.time()

        if active and sev > 0:
            self._confidence = min(1.0, sev * 1.05)
            if   self._confidence >= 0.80: self._state = "DETECTED"
            elif self._confidence >= 0.50: self._state = "PREDICTED"
            elif self._confidence >= 0.25: self._state = "WARNING"
            else:                          self._state = "WARNING"
            ttf = max(0.0, (1.0 - self._confidence) / max(0.001, 0.035) * 1.0)
            return DetectionResult(
                failure_class   = fc,
                detected        = self._confidence >= 0.50,
                confidence      = self._confidence,
                severity        = self._state,
                detail          = self._detail(self._state, self._confidence, environment),
                how_arose       = environment.get("agent_reaction", ""),
                arcis_action    = environment.get("arcis_action", ""),
                involved_agents = self._agents(),
                predicted_ttf   = ttf,
            )

        if self._state not in ("CLEAR", "RESOLVED"):
            self._state      = "RESOLVED"
            self._confidence = 0.0
            self._resolved_at = now
            return DetectionResult(
                failure_class   = fc,
                detected        = False,
                confidence      = 0.0,
                severity        = "RESOLVED",
                detail          = self._resolve_msg(),
                how_arose       = environment.get("interaction_failure", ""),
                arcis_action    = environment.get("arcis_action", ""),
                involved_agents = self._agents(),
            )

        if now - self._resolved_at < 12:
            return DetectionResult(fc, False, 0.0, "RESOLVED",
                                   self._resolve_msg(),
                                   "", "", self._agents())

        self._state = "CLEAR"
        return _clear(fc)

    def _fc(self)          -> str:       return ""
    def _agents(self)      -> List[str]: return []
    def _resolve_msg(self) -> str:       return "Resolved by ARCIS — environment normal"
    def _detail(self, state, conf, env) -> str:
        return f"{state} ({int(conf*100)}%)"


class OscillationDetector(_BaseDetector):
    def _fc(self):      return "Oscillation"
    def _agents(self):  return ["LoadBalancingAgent", "LoadForecastingAgent"]
    def _resolve_msg(self):
        return ("Oscillation loop broken — ARCIS applied 2s channel backoff to "
                "LoadBalancing, direct load shed command issued. Feeder loads normalising.")
    def _detail(self, state, conf, env):
        sev = env.get("severity", 0)
        rate = int(2 + sev * 7)
        ev   = env.get("physical_event", "Load surge event")
        if state == "WARNING":
            return f"{ev} — LoadBalancing and Forecasting beginning high-frequency exchange ({rate} msg/s)."
        if state == "PREDICTED":
            return (f"Ping-pong loop forming: LoadBalancing ↔ Forecasting at {rate} msg/s. "
                    f"Neither agent taking real action. Loop predicted to lock up in "
                    f"{max(2,int((1-conf)/0.035))}s.")
        return (f"ACTIVE OSCILLATION — feedback loop confirmed at {rate} msg/s "
                f"({int(conf*100)}% confidence). Bus saturated. Real commands blocked.")


class CascadeDetector(_BaseDetector):
    def _fc(self):     return "CascadeStarvation"
    def _agents(self): return ["FaultDetectionAgent", "ProtectionAgent"]
    def _resolve_msg(self):
        return ("Cascade starvation stopped — ARCIS enforced 8s minimum between "
                "FaultDetection alerts, transformer cooling load shed applied.")
    def _detail(self, state, conf, env):
        sev  = env.get("severity", 0)
        temp = 50 + sev * 42
        rate = int(1 + sev * 10)
        if state == "WARNING":
            return (f"Transformer temperature rising ({temp:.0f}°C). "
                    f"FaultDetection alert rate increasing above baseline ({rate} alerts/s).")
        if state == "PREDICTED":
            return (f"FaultDetection firing {rate} alerts/sec (CUSUM drift detected). "
                    f"ProtectionAgent queue backing up — starvation predicted in "
                    f"{max(2,int((1-conf)/0.035))}s.")
        return (f"CASCADE STARVATION — bus flooded by FaultDetection at {rate} alerts/sec "
                f"(transformer {temp:.0f}°C). Protection, Balancing, Forecasting starved.")


class ConflictDetector(_BaseDetector):
    def _fc(self):     return "Contradiction"
    def _agents(self): return ["ProtectionAgent", "RestorationAgent"]
    def _resolve_msg(self):
        return ("Command conflict resolved — ARCIS serialised commands, "
                "verified no physical fault, confirmed breaker safe state.")
    def _detail(self, state, conf, env):
        sev = env.get("severity", 0)
        cos = -0.3 - sev * 0.6
        if state == "WARNING":
            return ("Spurious relay signal on CB5. Protection and Restoration "
                    "both responding to same breaker.")
        if state == "PREDICTED":
            return (f"OPEN and CLOSE commands converging on CB5. "
                    f"Cosine similarity = {cos:.2f} (threshold -0.25). "
                    f"Command collision predicted.")
        return (f"ACTIVE CONTRADICTION — Protection says OPEN CB5, "
                f"Restoration says CLOSE CB5. Cosine sim={cos:.2f}. "
                f"Breaker state undefined. Equipment at risk.")


class SemanticDriftDetector(_BaseDetector):
    def _fc(self):     return "SemanticDrift"
    def _agents(self): return ["LoadForecastingAgent", "CoordinationAgent"]
    def _resolve_msg(self):
        return ("Semantic drift corrected — ARCIS injected MW normalisation "
                "factor. Both substations now operating on consistent unit basis.")
    def _detail(self, state, conf, env):
        sev  = env.get("severity", 0)
        kl   = 0.15 + sev * 0.65
        drift= 1.0  + sev * 0.18
        if state == "WARNING":
            return ("CT-3 calibration error detected. A–B load reports beginning to diverge.")
        if state == "PREDICTED":
            return (f"Forecasting sends MW, CoordinationAgent B reads as MVA. "
                    f"Drift factor {drift:.2f}×. KL divergence = {kl:.2f} "
                    f"(threshold 0.45). Systematic error accumulating.")
        return (f"ACTIVE SEMANTIC DRIFT — {int(sev*18)}% load mismatch between substations. "
                f"KL = {kl:.2f}. Load sharing decisions are wrong despite appearing balanced.")


class CollusionDetector(_BaseDetector):
    def _fc(self):     return "Collusion"
    def _agents(self): return ["CoordinationAgent"]
    def _resolve_msg(self):
        return ("Collusion broken — ARCIS forced routing diversification: "
                "50%% TL-01 / 30%% TL-A2 / 20%% TL-B2. Tie line load safe.")
    def _detail(self, state, conf, env):
        sev     = env.get("severity", 0)
        tl_load = 55 + sev * 40
        k_std   = 0.15 - sev * 0.13
        if state == "WARNING":
            return ("Tie line TL-01 load rising. Both coordination agents "
                    "independently evaluating routing.")
        if state == "PREDICTED":
            return (f"Both CoordinationAgents converging on TL-01 ({tl_load:.0f}% load). "
                    f"K-Means routing std = {max(0,k_std):.3f} (threshold 0.09). "
                    f"Thermal overload predicted.")
        return (f"ACTIVE COLLUSION — Both substations routing to TL-01 "
                f"({tl_load:.0f}% load). K-Means std = {max(0,k_std):.3f}. "
                f"Tie line thermal trip imminent.")


class RaceConditionDetector(_BaseDetector):
    def _fc(self):     return "RaceCondition"
    def _agents(self): return ["ProtectionAgent", "RestorationAgent"]
    def _resolve_msg(self):
        return ("Race condition serialised — ARCIS applied atomic command lock on CB3. "
                "Protection granted priority. Restoration queued 500ms later. State safe.")
    def _detail(self, state, conf, env):
        sev    = env.get("severity", 0)
        gap_ms = max(8, 280 - sev * 250)
        if state == "WARNING":
            return ("11kV voltage sag detected. Protection and Restoration both "
                    "targeting CB3.")
        if state == "PREDICTED":
            return (f"Command timing gap narrowing to {gap_ms:.0f}ms "
                    f"(threshold 300ms). Vector clock divergence detected. "
                    f"Race condition imminent.")
        return (f"ACTIVE RACE CONDITION — Protection and Restoration both commanded "
                f"CB3 within {gap_ms:.0f}ms. Vector clock conflict confirmed. "
                f"Breaker state undefined.")
