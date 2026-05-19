# config.py
import os

# ── Groq API ──────────────────────────────────────────────────────────────────
# Get free key at https://console.groq.com
# Set environment variable: set GROQ_API_KEY=your_key_here
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL     = "llama-3.3-70b-versatile"
GROQ_ENABLED   = bool(GROQ_API_KEY)  # auto-disables if no key set

# ── Simulation timing ─────────────────────────────────────────────────────────
AGENT_TICK_SECONDS   = 1.5
PHYSICS_TICK_SECONDS = 0.5
ARCIS_TICK_SECONDS   = 2.0
DASHBOARD_PUSH_SEC   = 1.0

# ── Substation layout ─────────────────────────────────────────────────────────
# Sub A: urban high-density load centre
# Sub B: mixed renewable + agricultural load with solar farm
SUBSTATION_A_ZONE = "Urban High-Density Load Centre"
SUBSTATION_B_ZONE = "Mixed Renewable + Agricultural (Solar Farm)"

# ── Transformer thresholds (IEC 60076) ───────────────────────────────────────
TR_TEMP_NOMINAL  = 40.0
TR_TEMP_WARNING  = 85.0
TR_TEMP_CRITICAL = 95.0
TR_TEMP_TRIP     = 100.0
TR_THERMAL_TAU   = 22.0

# ── Feeder limits ─────────────────────────────────────────────────────────────
FEEDER_RATED_MW      = 10.0
FEEDER_WARNING_PCT   = 0.85
FEEDER_OVERLOAD_PCT  = 1.00

# ── Relay settings ────────────────────────────────────────────────────────────
RELAY_PICKUP_FACTOR  = 1.2
RELAY_TRIP_DELAY_SEC = 0.2

# ── Failure injection ─────────────────────────────────────────────────────────
INJECT_MIN_SECONDS   = 50   # must be > STORY_HOLD_SECONDS (40s) + buffer
INJECT_MAX_SECONDS   = 80

# ── ARCIS detector thresholds ─────────────────────────────────────────────────
OSC_MIN_ALTERNATIONS = 5
OSC_WINDOW_SEC       = 15.0
CUSUM_LIMIT          = 10.0
CONFLICT_COS_THRESH  = -0.25
KL_DRIFT_THRESH      = 0.45
COLLUSION_STD_THRESH = 0.09
RACE_GAP_MS          = 300

# ── Intervention ──────────────────────────────────────────────────────────────
INTERVENTION_COOLDOWN   = 20
MONTE_CARLO_SIMULATIONS = 200