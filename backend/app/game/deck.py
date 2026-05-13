from __future__ import annotations

import random

RANKS = "23456789TJQKA"
SUITS = "CDHS"


def new_deck() -> list[str]:
    cards = [rank + suit for suit in SUITS for rank in RANKS]
    random.shuffle(cards)
    return cards


def card_label(card: str) -> str:
    rank, suit = card[0], card[1]
    suit_label = {"C": "♣", "D": "♦", "H": "♥", "S": "♠"}[suit]
    return f"{rank}{suit_label}"

