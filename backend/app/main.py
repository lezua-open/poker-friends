from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .game.engine import GameError
from .rooms import create_room, get_room, join_room


def get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return ["http://127.0.0.1:5173", "http://localhost:5173"]

app = FastAPI(title="Poker Friends")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connections: dict[str, dict[str, WebSocket]] = {}
auto_start_tasks: dict[str, asyncio.Task] = {}
action_tasks: dict[str, asyncio.Task] = {}
auto_start_task_deadlines: dict[str, float] = {}
action_task_deadlines: dict[str, float] = {}
ALLOWED_REACTIONS = {
    "👍": "好牌",
    "😅": "尴尬",
    "😂": "笑死",
    "🤔": "思考",
    "🔥": "厉害",
    "😭": "裂开",
    "👀": "看看",
    "🫡": "跟了",
    "💣": "全下？",
    "🏆": "漂亮",
}


class JoinRequest(BaseModel):
    nickname: str
    code: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rooms")
def create(payload: JoinRequest) -> dict[str, str]:
    room, player_id = create_room(payload.nickname)
    return {"code": room.code, "playerId": player_id}


@app.post("/rooms/{code}/join")
def join(code: str, payload: JoinRequest) -> dict[str, str]:
    room, player_id = join_room(code, payload.nickname)
    return {"code": room.code, "playerId": player_id}


@app.websocket("/ws/{code}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, code: str, player_id: str) -> None:
    await websocket.accept()
    try:
        room = get_room(code)
        room.players[player_id].connected = True
        connections.setdefault(room.code, {})[player_id] = websocket
        await broadcast(room.code)
        while True:
            payload = await websocket.receive_json()
            await handle_message(room.code, player_id, payload)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        if code.upper() in connections:
            connections[code.upper()].pop(player_id, None)
        try:
            room = get_room(code)
            if player_id in room.players:
                room.players[player_id].connected = False
            await broadcast(room.code)
        except GameError:
            pass


async def handle_message(code: str, player_id: str, payload: dict[str, Any]) -> None:
    room = get_room(code)
    message_type = payload.get("type")
    try:
        if message_type == "ready":
            room.set_ready(player_id, bool(payload.get("ready", True)))
        elif message_type == "start":
            room.start_hand(player_id)
        elif message_type == "action":
            room.act(player_id, str(payload.get("action")), payload.get("amount"))
        elif message_type == "chat":
            text = str(payload.get("text", ""))[:160].strip()
            if text:
                room.messages.append(f"CHAT|{room.players[player_id].nickname}|{text}")
        elif message_type == "reaction":
            emoji = str(payload.get("emoji", "")).strip()
            if emoji not in ALLOWED_REACTIONS:
                raise GameError("不支持的表情")
            label = ALLOWED_REACTIONS[emoji]
            room.messages.append(f"REACTION|{player_id}|{room.players[player_id].nickname}|{emoji}|{label}")
        else:
            raise GameError("不支持的消息")
    except GameError as exc:
        ws = connections.get(room.code, {}).get(player_id)
        if ws:
            await ws.send_json({"type": "error", "message": str(exc)})
    ensure_room_timers(room.code)
    await broadcast(room.code)


async def broadcast(code: str) -> None:
    room = get_room(code)
    stale: list[str] = []
    for player_id, websocket in connections.get(room.code, {}).items():
        try:
            await websocket.send_json({"type": "state", "state": room.snapshot(player_id)})
        except RuntimeError:
            stale.append(player_id)
    for player_id in stale:
        connections.get(room.code, {}).pop(player_id, None)


def ensure_room_timers(code: str) -> None:
    room = get_room(code)
    if room.auto_start_deadline is not None:
        task = auto_start_tasks.get(room.code)
        if task is None or task.done() or auto_start_task_deadlines.get(room.code) != room.auto_start_deadline:
            if task and not task.done():
                task.cancel()
            auto_start_task_deadlines[room.code] = room.auto_start_deadline
            auto_start_tasks[room.code] = asyncio.create_task(auto_start_when_ready(room.code, room.auto_start_deadline))
    else:
        task = auto_start_tasks.pop(room.code, None)
        auto_start_task_deadlines.pop(room.code, None)
        if task and task is not asyncio.current_task():
            task.cancel()

    if room.action_deadline is not None:
        task = action_tasks.get(room.code)
        if task is None or task.done() or action_task_deadlines.get(room.code) != room.action_deadline:
            if task and not task.done():
                task.cancel()
            action_task_deadlines[room.code] = room.action_deadline
            action_tasks[room.code] = asyncio.create_task(auto_action_on_timeout(room.code, room.action_deadline))
    else:
        task = action_tasks.pop(room.code, None)
        action_task_deadlines.pop(room.code, None)
        if task and task is not asyncio.current_task():
            task.cancel()


async def auto_start_when_ready(code: str, deadline: float) -> None:
    try:
        await asyncio.sleep(max(0, deadline - time.time()))
        room = get_room(code)
        if room.auto_start_deadline != deadline or not room.all_ready():
            return
        room.start_hand()
        ensure_room_timers(room.code)
        await broadcast(room.code)
    except (asyncio.CancelledError, GameError):
        return


async def auto_action_on_timeout(code: str, deadline: float) -> None:
    try:
        await asyncio.sleep(max(0, deadline - time.time()))
        room = get_room(code)
        if room.action_deadline != deadline:
            return
        room.auto_action()
        ensure_room_timers(room.code)
        await broadcast(room.code)
    except (asyncio.CancelledError, GameError):
        return


static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
