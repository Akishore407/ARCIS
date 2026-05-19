# core/physics.py
"""
Realistic substation physics.
Substation A: 5 transformers, 7 feeders, 10 CBs — urban load centre
Substation B: 5 transformers, 7 feeders, 10 CBs — solar farm + agricultural
"""
from __future__ import annotations
import math, random, time
from dataclasses import dataclass, field
from typing import List
from config import (TR_TEMP_NOMINAL, TR_TEMP_WARNING, TR_TEMP_CRITICAL,
                    TR_TEMP_TRIP, TR_THERMAL_TAU, FEEDER_RATED_MW,
                    FEEDER_WARNING_PCT, FEEDER_OVERLOAD_PCT)


@dataclass
class Transformer:
    name: str
    substation: str
    rating_kv: float
    rating_mva: float
    temperature: float = field(default=TR_TEMP_NOMINAL)
    load_pct: float    = 0.45
    online: bool       = True
    tripped: bool      = False
    trip_count: int    = 0
    _tau: float        = TR_THERMAL_TAU

    @property
    def t_final(self) -> float:
        return TR_TEMP_NOMINAL + 65.0 * self.load_pct

    def tick(self, dt: float):
        if not self.online:
            self.temperature += (TR_TEMP_NOMINAL - self.temperature) / self._tau * dt
            return
        delta = (self.t_final - self.temperature) / self._tau * dt
        noise = random.gauss(0, 0.08)
        self.temperature = max(TR_TEMP_NOMINAL, self.temperature + delta + noise)
        if self.temperature >= TR_TEMP_TRIP and not self.tripped:
            self.tripped = True
            self.online  = False
            self.trip_count += 1

    @property
    def status(self) -> str:
        if self.tripped:              return "TRIPPED"
        if not self.online:           return "OFFLINE"
        if self.temperature >= TR_TEMP_WARNING:  return "WARNING"
        return "NORMAL"

    def reset_trip(self):
        self.tripped = False
        self.online  = True

    def to_dict(self) -> dict:
        return {
            "name": self.name, "substation": self.substation,
            "rating_kv": self.rating_kv, "rating_mva": self.rating_mva,
            "temperature": round(self.temperature, 2),
            "load_pct": round(self.load_pct * 100, 1),
            "status": self.status, "trip_count": self.trip_count,
        }


@dataclass
class Feeder:
    name: str
    substation: str
    load_mw: float  = 5.0
    rated_mw: float = FEEDER_RATED_MW
    online: bool    = True
    is_solar: bool  = False   # Solar feeder on Substation B

    @property
    def load_pct(self) -> float:
        return self.load_mw / self.rated_mw if self.rated_mw > 0 else 0

    @property
    def status(self) -> str:
        if not self.online:                          return "OFFLINE"
        if self.load_pct >= FEEDER_OVERLOAD_PCT:     return "OVERLOAD"
        if self.load_pct >= FEEDER_WARNING_PCT:      return "WARNING"
        return "NORMAL"

    def to_dict(self) -> dict:
        return {
            "name": self.name, "substation": self.substation,
            "load_mw": round(self.load_mw, 2),
            "load_pct": round(self.load_pct * 100, 1),
            "rated_mw": self.rated_mw,
            "status": self.status,
            "is_solar": self.is_solar,
        }


@dataclass
class CircuitBreaker:
    name: str
    substation: str
    closed: bool         = True
    operation_count: int = 0

    @property
    def status(self) -> str:
        return "CLOSED" if self.closed else "OPEN"

    def trip(self):
        self.closed = False
        self.operation_count += 1

    def close(self):
        self.closed = True
        self.operation_count += 1

    def to_dict(self) -> dict:
        return {"name": self.name, "substation": self.substation,
                "status": self.status, "ops": self.operation_count}


class SubstationPhysics:
    """
    Substation A: urban high-density load centre
      - 5 transformers (T1-T5): 2×110kV/40MVA, 2×66kV/20MVA, 1×33kV/10MVA
      - 7 feeders (industrial, residential, commercial)
      - 10 circuit breakers

    Substation B: mixed renewable + agricultural with solar farm
      - 5 transformers (T6-T10): same ratings, different load profile
      - 7 feeders (3 agricultural, 2 solar, 2 residential)
      - 10 circuit breakers
    """
    def __init__(self, substation_id: str):
        sid = substation_id
        self.substation_id = sid
        self._last_tick = time.time()
        self._demand_phase = random.uniform(0, 2 * math.pi)
        self._solar_phase  = random.uniform(0, math.pi)   # solar arc

        if sid == "A":
            self.transformers: List[Transformer] = [
                Transformer("T1", sid, 110.0, 40.0, load_pct=0.58),
                Transformer("T2", sid, 110.0, 40.0, load_pct=0.52),
                Transformer("T3", sid,  66.0, 20.0, load_pct=0.61),
                Transformer("T4", sid,  66.0, 20.0, load_pct=0.47),
                Transformer("T5", sid,  33.0, 10.0, load_pct=0.55),
            ]
            self.feeders: List[Feeder] = [
                Feeder("Industrial_A1", sid, load_mw=6.2, rated_mw=10.0),
                Feeder("Industrial_A2", sid, load_mw=5.8, rated_mw=10.0),
                Feeder("Residential_A1", sid, load_mw=4.5, rated_mw=8.0),
                Feeder("Residential_A2", sid, load_mw=3.9, rated_mw=8.0),
                Feeder("Commercial_A1",  sid, load_mw=5.1, rated_mw=9.0),
                Feeder("Commercial_A2",  sid, load_mw=4.8, rated_mw=9.0),
                Feeder("Emergency_A",    sid, load_mw=1.2, rated_mw=4.0),
            ]
            self.breakers: List[CircuitBreaker] = [
                CircuitBreaker(f"CB{i}", sid) for i in range(1, 11)
            ]
        else:
            self.transformers = [
                Transformer("T6",  sid, 110.0, 40.0, load_pct=0.48),
                Transformer("T7",  sid, 110.0, 40.0, load_pct=0.44),
                Transformer("T8",  sid,  66.0, 20.0, load_pct=0.52),
                Transformer("T9",  sid,  66.0, 20.0, load_pct=0.41),
                Transformer("T10", sid,  33.0, 10.0, load_pct=0.38),
            ]
            self.feeders = [
                Feeder("Agricultural_B1", sid, load_mw=4.2, rated_mw=8.0),
                Feeder("Agricultural_B2", sid, load_mw=3.8, rated_mw=8.0),
                Feeder("Agricultural_B3", sid, load_mw=3.5, rated_mw=8.0),
                Feeder("Solar_Farm_B1",   sid, load_mw=3.0, rated_mw=6.0, is_solar=True),
                Feeder("Solar_Farm_B2",   sid, load_mw=2.8, rated_mw=6.0, is_solar=True),
                Feeder("Residential_B1",  sid, load_mw=3.2, rated_mw=7.0),
                Feeder("Residential_B2",  sid, load_mw=2.9, rated_mw=7.0),
            ]
            self.breakers = [
                CircuitBreaker(f"CB{i}", sid) for i in range(11, 21)
            ]

        # External stresses applied by environment injector
        self.stress_temp_boost:   float = 0.0
        self.stress_load_boost:   float = 0.0
        self.stress_feeder_boost: float = 0.0
        self.stress_voltage_sag:  float = 0.0
        self.voltage_pu:          float = 1.0   # per-unit bus voltage

    def tick(self):
        now = time.time()
        dt  = now - self._last_tick
        self._last_tick = now

        # Base demand: slow sinusoid mimicking load profile
        demand = 0.5 + 0.28 * math.sin(now / 35.0 + self._demand_phase)

        # Solar generation on Substation B (positive during "day" of sim cycle)
        solar_gen = max(0.0, 0.4 * math.sin(now / 60.0 + self._solar_phase))

        for tr in self.transformers:
            if tr.online:
                noise = random.gauss(0, 0.025)
                base  = demand + noise
                if self.substation_id == "B":
                    base = max(0.1, base - solar_gen * 0.2)
                tr.load_pct = max(0.05, min(0.99,
                    base + self.stress_load_boost + random.uniform(-0.04, 0.04)))
            tr.tick(dt)

        for feeder in self.feeders:
            if feeder.online:
                if feeder.is_solar:
                    feeder.load_mw = max(0.1, feeder.rated_mw * solar_gen *
                                         (0.8 + random.gauss(0, 0.05)))
                else:
                    noise = random.gauss(0, 0.18)
                    feeder.load_mw = max(0.3, min(
                        feeder.rated_mw * (1.0 + self.stress_feeder_boost),
                        feeder.rated_mw * demand + noise +
                        self.stress_feeder_boost * feeder.rated_mw * 0.5
                    ))

        # Update bus voltage
        self.voltage_pu = max(0.7, 1.0 - self.stress_voltage_sag +
                               random.gauss(0, 0.005))

    def total_load_mw(self) -> float:
        return sum(f.load_mw for f in self.feeders if f.online)

    def solar_generation_mw(self) -> float:
        return sum(f.load_mw for f in self.feeders
                   if f.online and f.is_solar)

    def to_dict(self) -> dict:
        return {
            "substation": self.substation_id,
            "transformers": [t.to_dict() for t in self.transformers],
            "feeders":      [f.to_dict() for f in self.feeders],
            "breakers":     [b.to_dict() for b in self.breakers],
            "total_load_mw":   round(self.total_load_mw(), 2),
            "solar_gen_mw":    round(self.solar_generation_mw(), 2),
            "voltage_pu":      round(self.voltage_pu, 4),
        }
