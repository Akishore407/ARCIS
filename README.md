# ARCIS — Autonomous Real-Time Cross-Agent Intelligence System
## Predictive Fault Management in Smart Grid Substations

---

## What ARCIS Does 

India's 2012 blackout — 620 million people — happened because every individual
component worked correctly, but their **interactions** caused the collapse.

ARCIS monitors the **conversations between AI agents** in a smart grid substation,
not the physical grid itself. It detects dangerous coordination patterns before
they cause any physical disruption, and intervenes autonomously.

---

## How the Simulation Works

```
Physical Environment Condition injected (random, every 35-70 seconds)
        ↓  (temperature rises, load surges, voltage sags)
Physics model responds realistically
        ↓  (transformers heat, feeders overload)
5 AI agents per substation react to changed sensor readings
        ↓  (alerts fire, commands issued, forecasts updated)
Agent interaction PATTERN changes (message rate, direction, content)
        ↓  (ARCIS observes passively — zero modification to agents)
ARCIS detects the emerging failure class
        ↓  (before any physical threshold is crossed)
ARCIS predicts time-to-failure using Monte Carlo simulation
        ↓
ARCIS selects minimum-disruption intervention strategy
        ↓
Intervention executed autonomously
        ↓
Environment returns to normal — story complete
```

---

## Six Physical Conditions That Cause Six Failure Classes

| Physical Event | Failure Class | What Happens |
|---|---|---|
| Transformer Thermal Runaway | **Cascade Starvation** | FaultDetection floods bus → other agents starved |
| Industrial Load Surge | **Oscillation** | LB ↔ Forecasting ping-pong loop |
| 11kV Busbar Voltage Sag | **Race Condition** | Protection + Restoration both command same breaker |
| Inter-substation Tie Line Overload | **Collusion** | Both CoordAgents route to same path |
| CT Metering Calibration Fault | **Semantic Drift** | MW vs MVA unit mismatch |
| Protection Relay Maloperation | **Contradiction** | OPEN + CLOSE on same breaker simultaneously |

---

## Setup

```bash
cd ARCIS
pip install -r requirements.txt
```

### Optional: Enable Groq LLM Reasoning
Get a free API key at https://console.groq.com
```bash
# Windows
set GROQ_API_KEY=your_key_here

# Then run
python main.py
```
Without the key, ARCIS works fully — agents use rule-based explanations instead of LLM.

---

## Run

```bash
python main.py
```

Open browser: **http://localhost:8000**

---

## What is seen in the simulation dashboard

1. **"What is happening right now" box** — 4-step plain English story:
   - Step 1: Physical event (e.g. "Transformer Thermal Runaway")
   - Step 2: How agents react (e.g. "FaultDetection firing 8 alerts/sec")
   - Step 3: What interaction failure forms (e.g. "Cascade Starvation")
   - Step 4: What ARCIS does (e.g. "Rate-limit applied, cooling initiated")

2. **Two substations** — 5 transformers, 7 feeders, 10 breakers each
   - Substation A: Urban load centre
   - Substation B: Solar farm + agricultural (solar generation shown live)

3. **ARCIS Detection Board** — 6 failure class cards each showing:
   - Confidence % (rising as physical event develops)
   - How the failure arose
   - What ARCIS did to resolve it

4. **Agent Interaction Graph** — D3 force graph, edges turn red when abnormal

5. **Intervention panel** — every ARCIS action with Monte Carlo disruption score

---

## Project Structure

```
ARCIS/
├── main.py                        Entry point
├── config.py                      All constants + Groq API key
├── requirements.txt
├── core/
│   ├── message.py                 Message dataclass
│   ├── message_bus.py             Async pub/sub bus
│   ├── vector_clock.py            Lamport vector clocks
│   ├── physics.py                 Transformer/feeder/breaker physics
│   ├── interaction_graph.py       Live edge weight computation
│   ├── environment.py             Physical condition catalogue
│   ├── arcis.py                   ARCIS meta-layer
│   └── groq_client.py             Groq API (Llama 3.3-70B)
├── agents/
│   ├── base_agent.py
│   ├── fault_detection_agent.py   Isolation Forest anomaly detection
│   ├── protection_agent.py        Relay logic + LLM consequence reasoning
│   ├── load_balancing_agent.py    NetworkX graph optimisation
│   ├── load_forecasting_agent.py  ARIMA + EWMA (LSTM-style)
│   ├── restoration_agent.py       Sequential planning + LLM
│   └── coordination_agent.py      Inter-substation coordination
├── detectors/
│   └── all_detectors.py           6 detectors (Tarjan SCC, CUSUM,
│                                  Cosine sim, KL divergence,
│                                  K-Means, Vector clocks)
├── prediction/
│   └── failure_predictor.py       Multi-signal prediction engine
├── intervention/
│   └── intervention_engine.py     Monte Carlo counterfactual simulation
├── injection/
│   └── failure_injector.py        Physical environment condition injector
└── dashboard/
    ├── app.py                     FastAPI + WebSocket
    └── templates/index.html       Story-driven real-time dashboard
```
