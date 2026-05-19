# agents/load_forecasting_agent.py
"""
ARIMA for short-term trend + simple LSTM-style EWMA for multi-horizon.
Groq explains forecast and confidence.
"""
from __future__ import annotations
import collections, math, time
import numpy as np
from agents.base_agent import BaseAgent
from core.message import MessageType, Priority
from core.groq_client import llm_reason, FORECASTING_SYSTEM


class LoadForecastingAgent(BaseAgent):
    ALPHA = 0.18   # EWMA smoothing

    def __init__(self, agent_id, substation, bus, physics):
        super().__init__(agent_id, substation, bus, physics)
        self._history: collections.deque = collections.deque(maxlen=80)
        self._smoothed: float = physics.total_load_mw()
        self._forecast_mw: float = self._smoothed
        self.forecasts_sent = 0
        # Unit drift injection flag
        self.inject_unit_drift = False
        self._drift_factor = 1.0

    async def tick(self):
        current = self.physics.total_load_mw()
        ts = time.time()
        self._history.append((ts, current))

        # EWMA (LSTM-style exponential smoothing)
        self._smoothed = (self.ALPHA * current +
                          (1 - self.ALPHA) * self._smoothed)

        # ARIMA-style: add linear trend over last 20 readings
        trend = self._arima_trend()
        self._forecast_mw = self._smoothed + trend * 5

        # Apply drift if injected (MW → MVA confusion)
        if self.inject_unit_drift:
            self._drift_factor = min(1.18, self._drift_factor + 0.008)
        else:
            self._drift_factor = max(1.0, self._drift_factor - 0.03)

        forecast_out = self._forecast_mw * self._drift_factor
        unit = "MVA" if self.inject_unit_drift else "MW"
        conf = self._confidence()

        reason = await llm_reason(
            FORECASTING_SYSTEM,
            f"Current load={current:.1f}MW, EWMA={self._smoothed:.1f}MW, "
            f"ARIMA trend={trend:+.3f}, 5-tick forecast={forecast_out:.1f}{unit}, "
            f"confidence={conf:.2f}. Summarise.",
            fallback=f"Forecast {forecast_out:.1f}{unit} (conf={conf:.2f})"
        ) if self.forecasts_sent % 5 == 0 else self.last_llm_reason

        if reason:
            self.last_llm_reason = reason

        await self.send("LoadBalancingAgent", MessageType.FORECAST, {
            "predicted_mw": round(forecast_out, 2),
            "current_mw":   round(current, 2),
            "smoothed_mw":  round(self._smoothed, 2),
            "trend":        round(trend, 4),
            "unit":         unit,
            "confidence":   round(conf, 3),
            "solar_gen":    round(self.physics.solar_generation_mw(), 2),
        }, Priority.MEDIUM, reason or "")
        self.forecasts_sent += 1

        await self.broadcast(MessageType.STATUS, {
            "agent": self.agent_id,
            "current_mw": round(current, 2),
            "forecast_mw": round(forecast_out, 2),
            "unit": unit,
            "confidence": round(conf, 3),
        }, Priority.LOW)

        self.health = 0.55 if self.inject_unit_drift else 1.0

    def _arima_trend(self) -> float:
        if len(self._history) < 10:
            return 0.0
        vals = [v for _, v in list(self._history)[-20:]]
        if len(vals) < 2:
            return 0.0
        return (vals[-1] - vals[0]) / len(vals)

    def _confidence(self) -> float:
        if len(self._history) < 10:
            return 0.5
        vals = [v for _, v in list(self._history)[-10:]]
        mean = sum(vals) / len(vals)
        std  = math.sqrt(sum((v - mean)**2 for v in vals) / len(vals))
        return max(0.0, min(1.0, 1.0 - std / (mean + 0.001)))

    def status_dict(self):
        d = super().status_dict()
        d.update({"forecast_mw": round(self._forecast_mw, 2),
                  "forecasts_sent": self.forecasts_sent,
                  "unit_drift": self.inject_unit_drift})
        return d
