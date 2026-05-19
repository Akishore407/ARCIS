# dashboard/app.py
from __future__ import annotations
import asyncio, json, time
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI(title="ARCIS Dashboard")

_arcis = _substations = _injector = _event_log = None
_connected_ws: Set[WebSocket] = set()


def init(arcis, substations, injector, event_log):
    global _arcis, _substations, _injector, _event_log
    _arcis = arcis
    _substations = substations
    _injector = injector
    _event_log = event_log


@app.get("/", response_class=HTMLResponse)
async def index():
    p = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(p.read_text(encoding="utf-8"))


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connected_ws.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _connected_ws.discard(websocket)


async def push_loop():
    global _connected_ws
    while True:
        await asyncio.sleep(1.0)
        if not _connected_ws:
            continue
        try:
            data = json.dumps(_build_payload())
            dead = set()
            for ws in list(_connected_ws):
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.add(ws)
            _connected_ws -= dead
        except Exception:
            pass


def _build_payload() -> dict:
    subs_data = {}
    for sid, sub in (_substations or {}).items():
        subs_data[sid] = {
            "physics":   sub["physics"].to_dict(),
            "agents":    {n: a.status_dict() for n, a in sub["agents"].items()},
            "zone":      sub.get("zone", ""),
            "bus_rate":  round(sub["bus"].messages_per_second(), 1),
            "bus_total": sub["bus"].total_messages,
        }
    arcis_snap      = _arcis.snapshot()  if _arcis    else {}
    injector_status = _injector.status() if _injector else {}
    return {
        "ts":          time.time(),
        "substations": subs_data,
        "arcis":       arcis_snap,
        "injector":    injector_status,
        "events":      list((_event_log or []))[-50:],
    }
