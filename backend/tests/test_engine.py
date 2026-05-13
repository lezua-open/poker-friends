import pytest

from app.game.engine import GameError, Room


def ready_room() -> Room:
    room = Room("TEST")
    first = room.add_player("Ada")
    second = room.add_player("Ben")
    room.set_ready(first.id)
    room.set_ready(second.id)
    room.start_hand()
    return room


def test_two_player_hand_starts_with_blinds_and_private_cards():
    room = ready_room()
    players = room.seat_order()

    assert room.phase == "preflop"
    assert room.dealer_seat == 0
    assert players[0].current_bet == room.small_blind
    assert players[1].current_bet == room.big_blind
    assert len(players[0].hand) == 2
    assert len(players[1].hand) == 2


def test_snapshot_hides_other_player_cards():
    room = ready_room()
    first, second = room.seat_order()

    snapshot = room.snapshot(first.id)
    first_view = snapshot["players"][first.seat]
    second_view = snapshot["players"][second.seat]

    assert first_view["hand"] == first.hand
    assert second_view["hand"] == ["BACK", "BACK"]


def test_only_host_can_start_hand():
    room = Room("TEST")
    host = room.add_player("Ada")
    guest = room.add_player("Ben")
    room.set_ready(host.id)
    room.set_ready(guest.id)

    with pytest.raises(GameError, match="只有房主"):
        room.start_hand(guest.id)


def test_start_requires_everyone_ready():
    room = Room("TEST")
    host = room.add_player("Ada")
    room.add_player("Ben")
    room.set_ready(host.id)

    with pytest.raises(GameError, match="所有玩家准备"):
        room.start_hand(host.id)


def test_ready_refills_busted_player_for_next_hand():
    room = Room("TEST")
    player = room.add_player("Ada")
    player.stack = 0

    room.set_ready(player.id)

    assert player.stack == room.initial_stack
    assert player.ready is True
