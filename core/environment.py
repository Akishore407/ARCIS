# core/environment.py
"""
Physical environment conditions injected into the substation.
Each condition stresses the physics model, which stresses agents,
which organically produces a cross-agent interaction failure pattern.

Flow:
  Physical condition injected (temp spike / load surge / voltage sag)
    → Physics model responds (transformers heat, feeders overload)
    → Agents react to sensor readings (alerts, commands, forecasts)
    → Interaction pattern changes (message rate, direction, content)
    → ARCIS detects the emerging interaction failure
    → ARCIS predicts and intervenes BEFORE physical threshold crossed
    → Environment normalises
"""
from __future__ import annotations
from dataclasses import dataclass, field
import time


@dataclass
class EnvCondition:
    key: str
    display_name: str
    substation: str          # "A", "B", or "BOTH"
    failure_class: str       # which ARCIS class will emerge

    # Plain-English story for dashboard
    physical_event: str      # what physical event is happening
    agent_reaction: str      # how agents start reacting
    interaction_failure: str # what cross-agent failure emerges
    arcis_action: str        # what ARCIS will do

    # Physics parameters
    temp_boost: float   = 0.0   # added to transformer load_pct per tick
    load_boost: float   = 0.0   # feeder load boost fraction
    volt_sag:   float   = 0.0   # voltage drop in per-unit

    # Runtime state
    severity:     float = 0.0
    active:       bool  = True
    injected_at:  float = field(default_factory=time.time)
    resolved_at:  float = 0.0

    def age(self) -> float:
        return time.time() - self.injected_at

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "substation": self.substation,
            "failure_class": self.failure_class,
            "physical_event": self.physical_event,
            "agent_reaction": self.agent_reaction,
            "interaction_failure": self.interaction_failure,
            "arcis_action": self.arcis_action,
            "severity": round(self.severity, 3),
            "active": self.active,
            "age_sec": round(self.age(), 1),
        }


# ── Catalogue ─────────────────────────────────────────────────────────────────

CONDITIONS = {

  "THERMAL_RUNAWAY": EnvCondition(
    key="THERMAL_RUNAWAY",
    display_name="Transformer Thermal Runaway",
    substation="A",
    failure_class="CascadeStarvation",
    physical_event=(
      "Ambient temperature spikes to 48°C (peak summer demand). "
      "Transformers T1 and T2 temperatures climb past 80°C warning threshold."
    ),
    agent_reaction=(
      "FaultDetectionAgent fires a thermal alert every second — far above its "
      "normal rate of one alert per 5 seconds. The message bus fills with alerts."
    ),
    interaction_failure=(
      "CASCADE STARVATION: FaultDetection floods the bus with alerts, "
      "starving ProtectionAgent, LoadBalancing, and Forecasting of processing time. "
      "Critical commands from other agents are delayed or dropped."
    ),
    arcis_action=(
      "ARCIS rate-limits FaultDetection (enforces 8s minimum between alerts), "
      "shed transformer load by 20%, and initiates forced cooling cycle."
    ),
    temp_boost=0.22,
    load_boost=0.18,
  ),

  "LOAD_SURGE": EnvCondition(
    key="LOAD_SURGE",
    display_name="Industrial Load Surge",
    substation="A",
    failure_class="Oscillation",
    physical_event=(
      "Large industrial facility comes online simultaneously — "
      "feeder loads spike to 140% rated capacity within 8 seconds."
    ),
    agent_reaction=(
      "LoadBalancingAgent sends shed commands to reduce demand. "
      "ForecastingAgent detects the anomaly and sends revised demand predictions. "
      "LoadBalancing replies asking for more data. Forecasting replies again..."
    ),
    interaction_failure=(
      "OSCILLATION: LoadBalancing and Forecasting enter a ping-pong loop — "
      "each reply triggers another reply. The loop runs at 6 messages/second, "
      "preventing either agent from taking any actual action."
    ),
    arcis_action=(
      "ARCIS detects the SCC loop via modified Tarjan algorithm, "
      "applies 2-second channel backoff to LoadBalancing, breaking the oscillation. "
      "Direct load shedding command issued to feeders."
    ),
    load_boost=0.38,
    temp_boost=0.10,
  ),

  "VOLTAGE_SAG": EnvCondition(
    key="VOLTAGE_SAG",
    display_name="11kV Busbar Voltage Sag",
    substation="A",
    failure_class="RaceCondition",
    physical_event=(
      "11kV busbar voltage drops to 9.1kV (severe under-voltage event) "
      "following a capacitor bank failure on the 33kV side."
    ),
    agent_reaction=(
      "ProtectionAgent detects under-voltage and issues OPEN command on CB3 "
      "to isolate the fault. RestorationAgent simultaneously detects the "
      "lost supply and issues CLOSE command on CB3 to restore it."
    ),
    interaction_failure=(
      "RACE CONDITION: Both Protection and Restoration command CB3 within 47ms. "
      "Vector clock analysis shows concurrent commands — whichever arrives last "
      "wins, making breaker state completely unpredictable. Equipment at risk."
    ),
    arcis_action=(
      "ARCIS detects the vector clock conflict, applies atomic command lock on CB3, "
      "grants Protection command priority, queues Restoration for 500ms later. "
      "Breaker state is now deterministic and safe."
    ),
    volt_sag=0.17,
    temp_boost=0.05,
  ),

  "TIE_LINE_OVERLOAD": EnvCondition(
    key="TIE_LINE_OVERLOAD",
    display_name="Inter-Substation Tie Line Overload",
    substation="BOTH",
    failure_class="Collusion",
    physical_event=(
      "Tie line TL-01 between Substation A and B approaches its 25 MVA thermal limit. "
      "Both coordination agents independently analyse routing options."
    ),
    agent_reaction=(
      "Substation A CoordinationAgent routes 9MW of excess load to TL-01. "
      "Substation B CoordinationAgent also routes 8MW of excess to TL-01. "
      "Neither knows what the other is doing — no cross-agent coordination."
    ),
    interaction_failure=(
      "COLLUSION: Both agents converge on TL-01 simultaneously. "
      "K-Means clustering shows routing diversity has collapsed to near-zero. "
      "TL-01 now carries 17MW against a 25 MVA limit — thermal trip imminent."
    ),
    arcis_action=(
      "ARCIS detects the routing convergence via behavioral clustering, "
      "forces diversification: 50% TL-01, 30% TL-A2, 20% TL-B2. "
      "TL-01 load reduced to safe levels. Alternative paths activated."
    ),
    load_boost=0.14,
  ),

  "METERING_FAULT": EnvCondition(
    key="METERING_FAULT",
    display_name="CT Metering Calibration Fault",
    substation="BOTH",
    failure_class="SemanticDrift",
    physical_event=(
      "Current transformer CT-3 develops a 15% calibration error. "
      "Substation A reports load in MW correctly. "
      "Substation B's CoordinationAgent reads those values as MVA (power factor = 1.0 assumed)."
    ),
    agent_reaction=(
      "ForecastingAgent on A sends: predicted_mw = 24.3 MW. "
      "CoordinationAgent on B reads: 24.3 MVA × 0.85 pf = 20.7 MW. "
      "The 15% systematic error compounds in every cross-substation calculation."
    ),
    interaction_failure=(
      "SEMANTIC DRIFT: Both agents speak MW but mean different things. "
      "KL divergence between their numeric distributions reaches 0.72 (threshold 0.45). "
      "Load sharing decisions are systematically wrong — the grid appears balanced but is not."
    ),
    arcis_action=(
      "ARCIS detects the KL divergence spike, traces it to the inter-substation channel, "
      "injects MW normalisation factor (÷ 0.85) into CoordinationAgent B. "
      "Both agents now operating on consistent unit basis."
    ),
    load_boost=0.08,
  ),

  "RELAY_MALOPERATION": EnvCondition(
    key="RELAY_MALOPERATION",
    display_name="Protection Relay Electromagnetic Maloperation",
    substation="A",
    failure_class="Contradiction",
    physical_event=(
      "Electromagnetic interference from nearby industrial equipment causes "
      "ProtectionAgent's relay to issue a spurious TRIP on CB5. "
      "No actual fault exists — the relay reading is false."
    ),
    agent_reaction=(
      "ProtectionAgent issues: OPEN CB5 (spurious trip command). "
      "RestorationAgent immediately detects the lost supply and responds: CLOSE CB5. "
      "Both agents are acting correctly given what each one knows."
    ),
    interaction_failure=(
      "CONTRADICTION: Protection says OPEN, Restoration says CLOSE — same breaker, same moment. "
      "Cosine similarity of command vectors = -0.91 (maximum conflict). "
      "The breaker receives physically opposing commands — equipment damage risk."
    ),
    arcis_action=(
      "ARCIS detects the command vector conflict, verifies no physical fault on CB5, "
      "suppresses the spurious OPEN command, confirms fault-free status, "
      "allows Restoration to maintain CLOSED state. Relay recalibration flagged."
    ),
    temp_boost=0.04,
  ),
}
