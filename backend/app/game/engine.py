from __future__ import annotations

import time
from dataclasses import dataclass, field
from secrets import token_hex

from .deck import new_deck
from .hand_eval import best_hand, best_hand_detail, hand_name


@dataclass
class Player:
    id: str
    nickname: str
    seat: int
    stack: int = 1000
    hand: list[str] = field(default_factory=list)
    current_bet: int = 0
    contribution: int = 0
    folded: bool = False
    all_in: bool = False
    acted: bool = False
    ready: bool = False
    connected: bool = True


class GameError(Exception):
    pass


class Room:
    def __init__(self, code: str, small_blind: int = 10, big_blind: int = 20, max_players: int = 6):
        self.code = code
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.initial_stack = 1000
        self.max_players = max_players
        self.players: dict[str, Player] = {}
        self.seats: list[str | None] = [None] * max_players
        self.host_id: str | None = None
        self.phase = "lobby"
        self.deck: list[str] = []
        self.community: list[str] = []
        self.dealer_seat = -1
        self.actor_seat: int | None = None
        self.current_bet = 0
        self.min_raise = big_blind
        self.messages: list[str] = []
        self.last_result = ""
        self.showdown_summary: list[dict] = []
        self.action_deadline: float | None = None
        self.auto_start_deadline: float | None = None

    def add_player(self, nickname: str) -> Player:
        if len(self.players) >= self.max_players:
            raise GameError("房间已满")
        for seat, player_id in enumerate(self.seats):
            if player_id is None:
                player = Player(id=token_hex(8), nickname=nickname[:24] or "玩家", seat=seat, stack=self.initial_stack)
                self.players[player.id] = player
                self.seats[seat] = player.id
                if self.host_id is None:
                    self.host_id = player.id
                self.messages.append(f"{player.nickname} 加入了房间")
                return player
        raise GameError("没有空座位")

    def set_ready(self, player_id: str, ready: bool = True) -> None:
        if self.phase not in {"lobby", "showdown"}:
            raise GameError("牌局进行中不能修改准备状态")
        player = self._player(player_id)
        if ready and player.stack <= 0:
            player.stack = self.initial_stack
            self.messages.append(f"{player.nickname} 筹码已补回 {self.initial_stack}")
        player.ready = ready
        status = "已准备" if ready else "取消了准备"
        self.messages.append(f"{player.nickname} {status}")
        self._refresh_auto_start()

    def start_hand(self, requester_id: str | None = None) -> None:
        if requester_id is not None and requester_id != self.host_id:
            raise GameError("只有房主可以开始游戏")
        if not self.all_ready():
            raise GameError("所有玩家准备后才能开始")
        seated = self.eligible_players()
        if len(seated) < 2:
            raise GameError("至少需要两名已准备玩家")
        self.phase = "preflop"
        self.deck = new_deck()
        self.community = []
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.last_result = ""
        self.showdown_summary = []
        self.auto_start_deadline = None
        self.dealer_seat = self._next_occupied_seat(self.dealer_seat)

        for player in self.players.values():
            player.hand = []
            player.current_bet = 0
            player.contribution = 0
            player.folded = not (player.ready and player.stack > 0)
            player.all_in = False
            player.acted = False
        for player in self.active_players(include_all_in=True):
            player.hand = [self.deck.pop(), self.deck.pop()]

        if len(self.active_players(include_all_in=True)) == 2:
            small = self.dealer_seat
            big = self._next_active_seat(small, include_all_in=True)
        else:
            small = self._next_active_seat(self.dealer_seat, include_all_in=True)
            big = self._next_active_seat(small, include_all_in=True)
        self._post_blind(small, self.small_blind)
        self._post_blind(big, self.big_blind)
        for player in self.active_players(include_all_in=True):
            player.ready = False
        self._set_actor(self._next_active_seat(big))
        self.messages.append("新一局开始")

    def act(self, player_id: str, action: str, amount: int | None = None) -> None:
        player = self._player(player_id)
        if self.phase not in {"preflop", "flop", "turn", "river"}:
            raise GameError("当前没有进行中的下注轮")
        if player.seat != self.actor_seat:
            raise GameError("还没轮到你行动")
        if player.folded or player.all_in:
            raise GameError("你现在不能行动")

        to_call = self.current_bet - player.current_bet
        if action == "fold":
            player.folded = True
            player.acted = True
            self.messages.append(f"{player.nickname} 弃牌")
        elif action == "check":
            if to_call != 0:
                raise GameError("有人下注时不能过牌")
            player.acted = True
            self.messages.append(f"{player.nickname} 过牌")
        elif action == "call":
            self._commit(player, min(to_call, player.stack))
            player.acted = True
            self.messages.append(f"{player.nickname} 跟注")
        elif action == "raise":
            if amount is None:
                raise GameError("请输入加注金额")
            self._raise_to(player, amount)
            self.messages.append(f"{player.nickname} 加注到 {player.current_bet}")
        elif action == "all_in":
            self._raise_to(player, player.current_bet + player.stack, all_in=True)
            self.messages.append(f"{player.nickname} 全下")
        else:
            raise GameError("未知操作")

        if self._only_one_player_left():
            self._award_uncontested()
            return
        if self._betting_round_complete():
            self._advance_street()
            return
        self._set_actor(self._next_active_seat(player.seat))

    def snapshot(self, viewer_id: str | None = None) -> dict:
        show_all = self.phase == "showdown"
        return {
            "code": self.code,
            "phase": self.phase,
            "smallBlind": self.small_blind,
            "bigBlind": self.big_blind,
            "dealerSeat": self.dealer_seat,
            "actorSeat": self.actor_seat,
            "actionDeadline": self.action_deadline,
            "autoStartDeadline": self.auto_start_deadline,
            "community": self.community,
            "pot": sum(p.contribution for p in self.players.values()),
            "currentBet": self.current_bet,
            "messages": self.messages[-30:],
            "lastResult": self.last_result,
            "showdownSummary": self.showdown_summary,
            "isHost": viewer_id == self.host_id,
            "hostId": self.host_id,
            "allReady": self.all_ready(),
            "canStart": viewer_id == self.host_id and self.all_ready(),
            "waitingPlayers": self.waiting_players(),
            "readyCount": len([p for p in self.eligible_players() if p.ready]),
            "eligibleCount": len(self.eligible_players()),
            "players": [self._player_view(player, viewer_id, show_all) if player else None for player in self._seat_players()],
            "actions": self.available_actions(viewer_id) if viewer_id else [],
        }

    def available_actions(self, player_id: str | None) -> list[dict]:
        if player_id is None or self.phase not in {"preflop", "flop", "turn", "river"}:
            return []
        player = self.players.get(player_id)
        if not player or player.seat != self.actor_seat:
            return []
        to_call = self.current_bet - player.current_bet
        actions = [{"type": "fold", "label": "弃牌"}]
        if to_call == 0:
            actions.append({"type": "check", "label": "过牌"})
        else:
            actions.append({"type": "call", "label": f"跟注 {min(to_call, player.stack)}"})
        if player.stack > to_call:
            min_to = self.current_bet + self.min_raise
            actions.append({"type": "raise", "label": "加注", "min": min_to, "max": player.current_bet + player.stack})
        if player.stack > 0:
            actions.append({"type": "all_in", "label": "全下"})
        return actions

    def seat_order(self) -> list[Player]:
        return [self.players[player_id] for player_id in self.seats if player_id is not None]

    def eligible_players(self) -> list[Player]:
        return [p for p in self.seat_order() if p.stack > 0]

    def waiting_players(self) -> list[str]:
        return [p.nickname for p in self.eligible_players() if not p.ready]

    def all_ready(self) -> bool:
        eligible = self.eligible_players()
        return self.phase in {"lobby", "showdown"} and len(eligible) >= 2 and all(p.ready for p in eligible)

    def auto_action(self) -> None:
        if self.phase not in {"preflop", "flop", "turn", "river"} or self.actor_seat is None:
            return
        player_id = self.seats[self.actor_seat]
        if player_id is None:
            return
        player = self.players[player_id]
        to_call = self.current_bet - player.current_bet
        self.act(player.id, "check" if to_call == 0 else "fold")

    def active_players(self, include_all_in: bool = False) -> list[Player]:
        return [
            p
            for p in self.seat_order()
            if not p.folded and (include_all_in or not p.all_in)
        ]

    def _player(self, player_id: str) -> Player:
        if player_id not in self.players:
            raise GameError("未知玩家")
        return self.players[player_id]

    def _seat_players(self) -> list[Player | None]:
        return [self.players[player_id] if player_id else None for player_id in self.seats]

    def _player_view(self, player: Player, viewer_id: str | None, show_all: bool) -> dict:
        visible_hand = player.hand if player.id == viewer_id or (show_all and not player.folded) else ["BACK"] * len(player.hand)
        return {
            "id": player.id,
            "nickname": player.nickname,
            "seat": player.seat,
            "stack": player.stack,
            "hand": visible_hand,
            "currentBet": player.current_bet,
            "contribution": player.contribution,
            "folded": player.folded,
            "allIn": player.all_in,
            "ready": player.ready,
            "connected": player.connected,
            "isYou": player.id == viewer_id,
        }

    def _post_blind(self, seat: int, amount: int) -> None:
        player = self.players[self.seats[seat]]
        self._commit(player, min(amount, player.stack))
        self.current_bet = max(self.current_bet, player.current_bet)

    def _commit(self, player: Player, amount: int) -> None:
        amount = max(0, min(amount, player.stack))
        player.stack -= amount
        player.current_bet += amount
        player.contribution += amount
        if player.stack == 0:
            player.all_in = True

    def _raise_to(self, player: Player, total_bet: int, all_in: bool = False) -> None:
        if total_bet <= self.current_bet and not all_in:
            raise GameError("加注金额必须高于当前下注")
        if total_bet > player.current_bet + player.stack:
            raise GameError("筹码不足")
        raise_size = total_bet - self.current_bet
        if raise_size < self.min_raise and total_bet < player.current_bet + player.stack:
            raise GameError(f"最小加注额是 {self.min_raise}")
        self._commit(player, total_bet - player.current_bet)
        if player.current_bet > self.current_bet:
            if raise_size >= self.min_raise:
                self.min_raise = raise_size
            self.current_bet = player.current_bet
            for other in self.active_players():
                other.acted = other.id == player.id
        else:
            player.acted = True

    def _betting_round_complete(self) -> bool:
        actors = self.active_players()
        if not actors:
            return True
        return all(p.acted and p.current_bet == self.current_bet for p in actors)

    def _advance_street(self) -> None:
        for player in self.players.values():
            player.current_bet = 0
            player.acted = False
        self.current_bet = 0
        self.min_raise = self.big_blind
        if self.phase == "preflop":
            self.community.extend([self.deck.pop(), self.deck.pop(), self.deck.pop()])
            self.phase = "flop"
        elif self.phase == "flop":
            self.community.append(self.deck.pop())
            self.phase = "turn"
        elif self.phase == "turn":
            self.community.append(self.deck.pop())
            self.phase = "river"
        else:
            self._showdown()
            return
        if len(self.active_players()) <= 1:
            self._advance_street()
            return
        self._set_actor(self._next_active_seat(self.dealer_seat))

    def _showdown(self) -> None:
        self.phase = "showdown"
        self._clear_actor()
        self.auto_start_deadline = None
        payouts = self._settle_pots()
        self.showdown_summary = self._build_showdown_summary(payouts)
        parts = [f"{self.players[player_id].nickname} 赢得 {amount}" for player_id, amount in payouts.items()]
        self.last_result = "，".join(parts) if parts else "没有赢家"
        self.messages.append(self.last_result)

    def _settle_pots(self) -> dict[str, int]:
        contributions = {p.id: p.contribution for p in self.seat_order() if p.contribution > 0}
        payouts = {p.id: 0 for p in self.seat_order()}
        previous = 0
        for level in sorted(set(contributions.values())):
            contributors = [pid for pid, value in contributions.items() if value >= level]
            pot_amount = (level - previous) * len(contributors)
            eligible = [self.players[pid] for pid in contributors if not self.players[pid].folded]
            best = max(best_hand(p.hand + self.community) for p in eligible)
            winners = [p for p in eligible if best_hand(p.hand + self.community) == best]
            share, remainder = divmod(pot_amount, len(winners))
            for index, winner in enumerate(winners):
                payout = share + (1 if index < remainder else 0)
                winner.stack += payout
                payouts[winner.id] += payout
            previous = level
        return {pid: amount for pid, amount in payouts.items() if amount > 0}

    def _only_one_player_left(self) -> bool:
        return len([p for p in self.seat_order() if not p.folded and p.hand]) == 1

    def _award_uncontested(self) -> None:
        winner = [p for p in self.seat_order() if not p.folded and p.hand][0]
        pot = sum(p.contribution for p in self.players.values())
        winner.stack += pot
        self.phase = "showdown"
        self._clear_actor()
        self.auto_start_deadline = None
        self.showdown_summary = [
            {
                "playerId": winner.id,
                "nickname": winner.nickname,
                "isWinner": True,
                "amount": pot,
                "handName": "未摊牌",
                "bestCards": [],
                "reason": "其他玩家都已弃牌",
            }
        ]
        self.last_result = f"{winner.nickname} 赢得 {pot}"
        self.messages.append(self.last_result)

    def _set_actor(self, seat: int) -> None:
        self.actor_seat = seat
        self.action_deadline = time.time() + 30

    def _clear_actor(self) -> None:
        self.actor_seat = None
        self.action_deadline = None

    def _refresh_auto_start(self) -> None:
        if self.all_ready():
            if self.auto_start_deadline is None:
                self.auto_start_deadline = time.time() + 10
                self.messages.append("所有玩家已准备，10 秒后自动开始")
        else:
            self.auto_start_deadline = None

    def _build_showdown_summary(self, payouts: dict[str, int]) -> list[dict]:
        summary = []
        for player in self.seat_order():
            if player.folded or not player.hand:
                continue
            score, cards = best_hand_detail(player.hand + self.community)
            name = hand_name(score)
            amount = payouts.get(player.id, 0)
            summary.append(
                {
                    "playerId": player.id,
                    "nickname": player.nickname,
                    "isWinner": amount > 0,
                    "amount": amount,
                    "handName": name,
                    "bestCards": cards,
                    "reason": f"{name}，最佳五张牌参与比较",
                }
            )
        return summary

    def _next_occupied_seat(self, after: int) -> int:
        for offset in range(1, self.max_players + 1):
            seat = (after + offset) % self.max_players
            if self.seats[seat] is not None and self.players[self.seats[seat]].stack > 0:
                return seat
        raise GameError("没有可用座位")

    def _next_active_seat(self, after: int, include_all_in: bool = False) -> int:
        for offset in range(1, self.max_players + 1):
            seat = (after + offset) % self.max_players
            player_id = self.seats[seat]
            if player_id is None:
                continue
            player = self.players[player_id]
            if not player.folded and (include_all_in or not player.all_in):
                return seat
        raise GameError("没有可行动的座位")
