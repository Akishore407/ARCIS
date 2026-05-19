# injection/failure_injector.py
from __future__ import annotations
import asyncio, random, time, copy
from typing import Dict, Optional
from core.environment import CONDITIONS, EnvCondition
from config import INJECT_MIN_SECONDS, INJECT_MAX_SECONDS


class FailureInjector:
    def __init__(self, substations: Dict[str, dict], event_log: list):
        self.substations  = substations
        self.event_log    = event_log
        self.running      = False
        self.inject_count = 0
        self._active: Optional[EnvCondition] = None
        self._severity_rate = 0.035   # per tick, so ~28 ticks to reach 1.0

    def active_flags(self) -> dict:
        if self._active and self._active.active:
            return {self._active.failure_class: True}
        return {}

    def get_active_condition(self) -> Optional[dict]:
        if self._active and self._active.active:
            return self._active.to_dict()
        return None

    def clear_failure(self, failure_class: str):
        if (self._active and
                self._active.failure_class == failure_class and
                self._active.active):
            self._resolve()

    async def run(self):
        self.running = True
        await asyncio.sleep(30)

        while self.running:
            await asyncio.sleep(1.0)
            if self._active and self._active.active:
                self._tick_physics()
                if self._active.age() > 60:
                    self._resolve()
            else:
                wait = random.uniform(INJECT_MIN_SECONDS, INJECT_MAX_SECONDS)
                await asyncio.sleep(wait)
                self._inject_new()

    def _inject_new(self):
        key = random.choice(list(CONDITIONS.keys()))
        tmpl = CONDITIONS[key]
        self._active = EnvCondition(
            key=tmpl.key,
            display_name=tmpl.display_name,
            substation=tmpl.substation,
            failure_class=tmpl.failure_class,
            physical_event=tmpl.physical_event,
            agent_reaction=tmpl.agent_reaction,
            interaction_failure=tmpl.interaction_failure,
            arcis_action=tmpl.arcis_action,
            temp_boost=tmpl.temp_boost,
            load_boost=tmpl.load_boost,
            volt_sag=tmpl.volt_sag,
            severity=0.0,
            active=True,
            injected_at=time.time(),
        )
        self.inject_count += 1
        cond = self._active
        self._log("INJECTION",
            f"🌡 PHYSICAL EVENT: {cond.display_name} — Substation {cond.substation}")
        self._log("INFO",
            f"   ↳ {cond.physical_event}")
        self._log("INFO",
            f"   ↳ Agents will react: {cond.agent_reaction[:80]}...")

    def _tick_physics(self):
        cond = self._active
        cond.severity = min(1.0, cond.severity + self._severity_rate)
        sev = cond.severity

        targets = (list(self.substations.keys())
                   if cond.substation == "BOTH"
                   else [cond.substation])

        for sid in targets:
            sub     = self.substations.get(sid)
            if not sub: continue
            physics = sub["physics"]
            agents  = sub["agents"]

            # Temperature stress
            if cond.temp_boost > 0:
                for tr in physics.transformers[:2]:
                    if tr.online:
                        tr.temperature = min(99.0,
                            tr.temperature + cond.temp_boost * sev)

            # Load stress
            if cond.load_boost > 0:
                physics.stress_load_boost   = cond.load_boost * sev
                physics.stress_feeder_boost = cond.load_boost * sev * 0.6

            # Voltage sag
            if cond.volt_sag > 0:
                physics.stress_voltage_sag = cond.volt_sag * sev

            # Agent-level effects at severity > 0.35
            if sev >= 0.35:
                self._agent_effects(cond, agents, physics, sev)

    def _agent_effects(self, cond, agents, physics, sev):
        fc = cond.failure_class

        if fc == "CascadeStarvation":
            fd = agents.get("FaultDetectionAgent")
            if fd:
                fd._flood_mode = True
                fd._last_alert = {}

        elif fc == "Oscillation":
            lb = agents.get("LoadBalancingAgent")
            if lb and sev > 0.5:
                lb._reply_cooldown = 0.0

        elif fc == "SemanticDrift":
            fa = agents.get("LoadForecastingAgent")
            ca = agents.get("CoordinationAgent")
            if fa: fa.inject_unit_drift    = True
            if ca: ca.inject_unit_mismatch = True

        elif fc == "Collusion":
            ca = agents.get("CoordinationAgent")
            if ca: ca.inject_tie_overload = True

        elif fc == "Contradiction" and sev > 0.5:
            pa = agents.get("ProtectionAgent")
            ra = agents.get("RestorationAgent")
            if pa and ra and physics.breakers and len(physics.breakers) >= 5:
                pa._pending_trips[physics.breakers[4].name] = time.time() + 0.1
                if not ra._sequence:
                    ra._start(physics.breakers[4].name)

        elif fc == "RaceCondition" and sev > 0.5:
            pa = agents.get("ProtectionAgent")
            ra = agents.get("RestorationAgent")
            if pa and ra and physics.breakers:
                pa._pending_trips[physics.breakers[0].name] = time.time() + 0.05
                if not ra._sequence:
                    ra._start(physics.breakers[0].name)

    def _resolve(self):
        cond = self._active
        if not cond: return
        cond.active = False
        cond.resolved_at = time.time()

        targets = (list(self.substations.keys())
                   if cond.substation == "BOTH"
                   else [cond.substation])

        for sid in targets:
            sub = self.substations.get(sid)
            if not sub: continue
            physics = sub["physics"]
            agents  = sub["agents"]

            # Restore physics
            physics.stress_load_boost   = 0.0
            physics.stress_feeder_boost = 0.0
            physics.stress_voltage_sag  = 0.0
            for tr in physics.transformers:
                tr.load_pct = max(0.30, tr.load_pct - 0.22)
            for f in physics.feeders:
                if not f.is_solar:
                    f.load_mw = max(2.0, f.load_mw * 0.75)

            # Clear agent flags
            fd = agents.get("FaultDetectionAgent")
            fa = agents.get("LoadForecastingAgent")
            ca = agents.get("CoordinationAgent")
            pa = agents.get("ProtectionAgent")
            lb = agents.get("LoadBalancingAgent")
            if fd: fd._flood_mode = False
            if fa: fa.inject_unit_drift    = False
            if ca: ca.inject_unit_mismatch = False
            if ca: ca.inject_tie_overload  = False
            if pa: pa.override_active      = False
            if lb: lb._reply_cooldown      = 0.0

        self._log("RESTORE",
            f"✅ ENVIRONMENT RESOLVED: {cond.display_name} — "
            f"active for {cond.age():.0f}s")

    def _log(self, etype: str, msg: str):
        self.event_log.append({"time": time.time(), "type": etype, "message": msg})
        if len(self.event_log) > 400:
            self.event_log.pop(0)

    def status(self) -> dict:
        return {
            "inject_count": self.inject_count,
            "running": self.running,
            "active": [self._active.failure_class] if self._active and self._active.active else [],
            "condition": self.get_active_condition(),
        }
