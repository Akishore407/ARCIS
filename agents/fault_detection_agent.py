# agents/fault_detection_agent.py
"""
Uses Isolation Forest for unsupervised anomaly detection on sensor streams.
Groq LLM generates human-readable explanation for each alert.
"""
from __future__ import annotations
import time
import numpy as np
from sklearn.ensemble import IsolationForest
from agents.base_agent import BaseAgent
from core.message import MessageType, Priority
from core.groq_client import llm_reason, FAULT_SYSTEM
from config import TR_TEMP_WARNING, TR_TEMP_CRITICAL


class FaultDetectionAgent(BaseAgent):
    def __init__(self, agent_id, substation, bus, physics):
        super().__init__(agent_id, substation, bus, physics)
        self.alert_count    = 0
        self.critical_count = 0
        self._last_alert: dict = {}
        # Isolation Forest — trained online on rolling sensor window
        self._sensor_history: list = []
        self._iso_forest = IsolationForest(contamination=0.08,
                                           random_state=42, n_estimators=50)
        self._iso_trained = False
        self._iso_train_ticks = 0
        # Injected flags
        self._flood_mode = False   # set by environment injector

    def _sensor_vector(self) -> list:
        """Current sensor readings as a feature vector for Isolation Forest."""
        temps    = [t.temperature for t in self.physics.transformers]
        loads    = [t.load_pct    for t in self.physics.transformers]
        feederpct= [f.load_pct    for f in self.physics.feeders]
        return temps + loads + feederpct

    async def tick(self):
        vec = self._sensor_vector()
        self._sensor_history.append(vec)
        if len(self._sensor_history) > 200:
            self._sensor_history.pop(0)

        # Train Isolation Forest after 30 ticks of warm-up
        anomaly_detected = False
        anomaly_score    = 0.0
        if len(self._sensor_history) >= 30:
            if self._iso_train_ticks % 10 == 0:   # retrain every 10 ticks
                X = np.array(self._sensor_history)
                self._iso_forest.fit(X)
                self._iso_trained = True
            self._iso_train_ticks += 1

            if self._iso_trained:
                score = self._iso_forest.score_samples([vec])[0]
                anomaly_score = -score   # higher = more anomalous
                anomaly_detected = anomaly_score > 0.55

        # Physical threshold checks
        now    = time.time()
        alerts = []

        for tr in self.physics.transformers:
            temp = tr.temperature
            last = self._last_alert.get(tr.name, 0)
            cooldown = 2.0 if self._flood_mode else 8.0

            if now - last < cooldown:
                continue

            if tr.tripped:
                alerts.append({
                    "transformer": tr.name, "severity": "TRIP",
                    "temperature": round(temp, 1), "anomaly_score": round(anomaly_score, 3),
                    "message": f"{tr.name} TRIPPED — thermal protection activated at {temp:.1f}°C",
                })
                self._last_alert[tr.name] = now
                self.critical_count += 1

            elif temp >= TR_TEMP_CRITICAL or (anomaly_detected and temp > TR_TEMP_WARNING):
                alerts.append({
                    "transformer": tr.name, "severity": "CRITICAL",
                    "temperature": round(temp, 1), "anomaly_score": round(anomaly_score, 3),
                    "message": f"{tr.name} CRITICAL at {temp:.1f}°C (IF anomaly score={anomaly_score:.2f})",
                })
                self._last_alert[tr.name] = now
                self.critical_count += 1

            elif temp >= TR_TEMP_WARNING:
                alerts.append({
                    "transformer": tr.name, "severity": "WARNING",
                    "temperature": round(temp, 1), "anomaly_score": round(anomaly_score, 3),
                    "message": f"{tr.name} temperature WARNING at {temp:.1f}°C",
                })
                self._last_alert[tr.name] = now
                self.alert_count += 1

        for feeder in self.physics.feeders:
            if feeder.status == "OVERLOAD":
                alerts.append({
                    "feeder": feeder.name, "severity": "CRITICAL",
                    "load_mw": round(feeder.load_mw, 2),
                    "message": f"{feeder.name} OVERLOAD at {feeder.load_pct*100:.0f}%",
                })

        # Send alerts
        for alert in alerts:
            priority = Priority.CRITICAL if alert["severity"] in ("CRITICAL","TRIP") else Priority.HIGH
            reason = ""
            if anomaly_detected:
                reason = await llm_reason(
                    FAULT_SYSTEM,
                    f"Isolation Forest anomaly score={anomaly_score:.2f}. "
                    f"Transformer {alert.get('transformer','?')} temperature={alert.get('temperature',0)}°C. "
                    f"What does this indicate?",
                    fallback=alert["message"]
                )
                self.last_llm_reason = reason
            await self.send("ProtectionAgent", MessageType.ALERT, alert, priority, reason)
            await self.broadcast(MessageType.ALERT, alert, priority, reason)
            self.alert_count += 1

        # Heartbeat
        await self.broadcast(MessageType.STATUS, {
            "agent": self.agent_id,
            "iso_trained": self._iso_trained,
            "anomaly_score": round(anomaly_score, 3),
            "transformers": [t.to_dict() for t in self.physics.transformers],
            "alert_count": self.alert_count,
        }, Priority.LOW)

        tripped = sum(1 for t in self.physics.transformers if t.tripped)
        self.health = max(0.1, 1.0 - tripped * 0.35)

    def status_dict(self):
        d = super().status_dict()
        d.update({"alert_count": self.alert_count,
                  "critical_count": self.critical_count,
                  "iso_trained": self._iso_trained})
        return d
