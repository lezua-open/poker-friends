from __future__ import annotations

import string
from random import choices

from .game.engine import GameError, Room

ROOMS: dict[str, Room] = {}


def create_room(nickname: str) -> tuple[Room, str]:
    code = _room_code()
    room = Room(code)
    ROOMS[code] = room
    player = room.add_player(nickname)
    return room, player.id


def join_room(code: str, nickname: str) -> tuple[Room, str]:
    room = get_room(code)
    player = room.add_player(nickname)
    return room, player.id


def get_room(code: str) -> Room:
    normalized = code.upper()
    if normalized not in ROOMS:
        raise GameError("房间不存在")
    return ROOMS[normalized]


def _room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(choices(alphabet, k=5))
        if code not in ROOMS:
            return code
