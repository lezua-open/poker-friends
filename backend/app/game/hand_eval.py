from __future__ import annotations

from collections import Counter
from itertools import combinations

RANK_VALUE = {rank: index + 2 for index, rank in enumerate("23456789TJQKA")}


def evaluate_five(cards: tuple[str, ...]) -> tuple[int, tuple[int, ...]]:
    ranks = sorted((RANK_VALUE[card[0]] for card in cards), reverse=True)
    suits = [card[1] for card in cards]
    counts = Counter(ranks)
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    unique = sorted(set(ranks), reverse=True)
    wheel = set(unique) == {14, 5, 4, 3, 2}
    straight_high = 5 if wheel else None
    if len(unique) == 5 and unique[0] - unique[4] == 4:
        straight_high = unique[0]
    flush = len(set(suits)) == 1

    if flush and straight_high:
        return (8, (straight_high,))
    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(rank for rank in ranks if rank != quad)
        return (7, (quad, kicker))
    if groups[0][1] == 3 and groups[1][1] == 2:
        return (6, (groups[0][0], groups[1][0]))
    if flush:
        return (5, tuple(ranks))
    if straight_high:
        return (4, (straight_high,))
    if groups[0][1] == 3:
        trip = groups[0][0]
        kickers = tuple(rank for rank in ranks if rank != trip)
        return (3, (trip, *kickers))
    if groups[0][1] == 2 and groups[1][1] == 2:
        pairs = tuple(sorted((groups[0][0], groups[1][0]), reverse=True))
        kicker = max(rank for rank in ranks if rank not in pairs)
        return (2, (*pairs, kicker))
    if groups[0][1] == 2:
        pair = groups[0][0]
        kickers = tuple(rank for rank in ranks if rank != pair)
        return (1, (pair, *kickers))
    return (0, tuple(ranks))


def best_hand(cards: list[str]) -> tuple[int, tuple[int, ...]]:
    if len(cards) < 5:
        raise ValueError("At least five cards are required")
    return max(evaluate_five(tuple(combo)) for combo in combinations(cards, 5))


def best_hand_detail(cards: list[str]) -> tuple[tuple[int, tuple[int, ...]], list[str]]:
    if len(cards) < 5:
        raise ValueError("At least five cards are required")
    best_combo = max(combinations(cards, 5), key=lambda combo: evaluate_five(tuple(combo)))
    return evaluate_five(tuple(best_combo)), list(best_combo)


def hand_name(score: tuple[int, tuple[int, ...]]) -> str:
    return [
        "高牌",
        "一对",
        "两对",
        "三条",
        "顺子",
        "同花",
        "葫芦",
        "四条",
        "同花顺",
    ][score[0]]
