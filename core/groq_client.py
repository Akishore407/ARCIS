# core/groq_client.py
"""
Groq API client — Llama 3.3-70B for agent reasoning.
Sub-200ms inference for real-time simulation loop.
Falls back to rule-based explanation if API key not set or call fails.
"""
from __future__ import annotations
import asyncio, time
from typing import Optional
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_ENABLED

_client = None

def _get_client():
    global _client
    if _client is None and GROQ_ENABLED:
        try:
            from groq import Groq
            _client = Groq(api_key=GROQ_API_KEY)
        except Exception:
            pass
    return _client


async def llm_reason(system_prompt: str, user_prompt: str,
                     max_tokens: int = 120,
                     fallback: str = "") -> str:
    """
    Call Groq API asynchronously.
    Returns LLM response or fallback string if unavailable.
    Timeout: 3 seconds (must not block simulation loop).
    """
    if not GROQ_ENABLED:
        return fallback

    client = _get_client()
    if client is None:
        return fallback

    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )),
            timeout=3.0
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return fallback


# ── Pre-built prompts for each agent ─────────────────────────────────────────

FAULT_SYSTEM = (
    "You are the Fault Detection Agent of a smart power substation. "
    "You monitor transformer temperatures and feeder currents. "
    "Respond in ONE sentence explaining what you detected and why it matters. "
    "Be concise and technical."
)

PROTECTION_SYSTEM = (
    "You are the Protection Agent of a smart power substation. "
    "You evaluate whether to trip circuit breakers. "
    "Respond in ONE sentence: state what action you took and the consequence avoided. "
    "Be concise and technical."
)

BALANCING_SYSTEM = (
    "You are the Load Balancing Agent of a smart power substation. "
    "You redistribute load across feeders using droop control. "
    "Respond in ONE sentence explaining the rebalancing decision and its effect. "
    "Be concise and technical."
)

FORECASTING_SYSTEM = (
    "You are the Load Forecasting Agent using ARIMA and LSTM models. "
    "Respond in ONE sentence summarising the demand forecast and confidence level. "
    "Be concise and technical."
)

RESTORATION_SYSTEM = (
    "You are the Restoration Agent of a smart power substation. "
    "You plan safe breaker reclosure sequences after a fault. "
    "Respond in ONE sentence explaining the restoration step and why this sequence is safe. "
    "Be concise and technical."
)

ARCIS_SYSTEM = (
    "You are ARCIS — the Autonomous Real-Time Cross-Agent Intelligence System. "
    "You monitor cross-agent interaction patterns in smart grid substations. "
    "Respond in ONE sentence explaining what failure pattern you detected and what intervention you applied. "
    "Be specific about which agents are involved. Be concise."
)
