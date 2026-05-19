# main.py
from __future__ import annotations
import asyncio, uvicorn
from core.message_bus import MessageBus, InterSubstationBus
from core.physics import SubstationPhysics
from core.arcis import ARCISMetaLayer
from agents.fault_detection_agent  import FaultDetectionAgent
from agents.protection_agent       import ProtectionAgent
from agents.load_balancing_agent   import LoadBalancingAgent
from agents.load_forecasting_agent import LoadForecastingAgent
from agents.restoration_agent      import RestorationAgent
from agents.coordination_agent     import CoordinationAgent
from injection.failure_injector    import FailureInjector
import dashboard.app as dash_app
from config import PHYSICS_TICK_SECONDS, GROQ_ENABLED, SUBSTATION_A_ZONE, SUBSTATION_B_ZONE

EVENT_LOG: list = []


def build_substation(sid: str, inter_bus: InterSubstationBus) -> dict:
    bus     = MessageBus(sid)
    physics = SubstationPhysics(sid)
    agents = {
        "FaultDetectionAgent":  FaultDetectionAgent ("FaultDetectionAgent",  sid, bus, physics),
        "ProtectionAgent":      ProtectionAgent      ("ProtectionAgent",      sid, bus, physics),
        "LoadBalancingAgent":   LoadBalancingAgent   ("LoadBalancingAgent",   sid, bus, physics),
        "LoadForecastingAgent": LoadForecastingAgent ("LoadForecastingAgent", sid, bus, physics),
        "RestorationAgent":     RestorationAgent     ("RestorationAgent",     sid, bus, physics),
        "CoordinationAgent":    CoordinationAgent    ("CoordinationAgent",    sid, bus, physics, inter_bus),
    }
    zone = SUBSTATION_A_ZONE if sid == "A" else SUBSTATION_B_ZONE
    return {"sid": sid, "bus": bus, "physics": physics, "agents": agents, "zone": zone}


async def physics_loop(substations: dict):
    while True:
        for sub in substations.values():
            sub["physics"].tick()
        await asyncio.sleep(PHYSICS_TICK_SECONDS)


async def log_loop(substations: dict, event_log: list):
    import time
    seen_trips: set = set()
    seen_restorations: set = set()
    while True:
        await asyncio.sleep(2.0)
        for sid, sub in substations.items():
            for tr in sub["physics"].transformers:
                key = f"{sid}-{tr.name}-{tr.trip_count}"
                if tr.trip_count > 0 and key not in seen_trips:
                    seen_trips.add(key)
                    event_log.append({
                        "time": time.time(), "type": "PHYSICS",
                        "message": f"[{sid}] {tr.name} TRIPPED — temp {tr.temperature:.1f}C"
                    })
            ra = sub["agents"].get("RestorationAgent")
            if ra:
                key = f"{sid}-restore-{ra.restorations_completed}"
                if ra.restorations_completed > 0 and key not in seen_restorations:
                    seen_restorations.add(key)
                    event_log.append({
                        "time": time.time(), "type": "RESTORE",
                        "message": f"[{sid}] Restoration #{ra.restorations_completed} complete — grid stable"
                    })


async def main():
    inter_bus = InterSubstationBus()

    substations = {
        "A": build_substation("A", inter_bus),
        "B": build_substation("B", inter_bus),
    }

    arcis    = ARCISMetaLayer(substations, inter_bus)
    injector = FailureInjector(substations, EVENT_LOG)

    # Cross-wire references
    arcis.injector            = injector
    arcis.intervener.injector = injector

    dash_app.init(arcis, substations, injector, EVENT_LOG)

    groq_status = "ENABLED (Groq API key found)" if GROQ_ENABLED else "DISABLED (set GROQ_API_KEY env var for LLM reasoning)"

    print("\n" + "="*65)
    print("  ARCIS — Autonomous Real-Time Cross-Agent Intelligence System")
    print("  Predictive Fault Management in Smart Grid Substations")
    print(f"  Groq LLM: {groq_status}")
    print(f"  Substation A: {SUBSTATION_A_ZONE}")
    print(f"  Substation B: {SUBSTATION_B_ZONE}")
    print("  Dashboard -> http://localhost:8000")
    print("="*65 + "\n")

    config = uvicorn.Config(dash_app.app, host="0.0.0.0", port=8000,
                            log_level="warning")
    server = uvicorn.Server(config)

    agent_coros = [
        agent.run()
        for sub in substations.values()
        for agent in sub["agents"].values()
    ]

    await asyncio.gather(
        server.serve(),
        physics_loop(substations),
        arcis.run(),
        injector.run(),
        dash_app.push_loop(),
        log_loop(substations, EVENT_LOG),
        *agent_coros,
    )


if __name__ == "__main__":
    asyncio.run(main())
