"""Stratégie Big Money pour Dopynion."""

from __future__ import annotations

from dopynion.cards import Card
from dopynion.data_model import CardName, Cards, Game, Player

PLAYER_NAME = "Groupe 5"
PROVINCES_LEFT_FOR_DUCHY = 5

# game_id -> True si on a déjà effectué un achat ce tour
_bought_this_turn: dict[str, bool] = {}


def reset_turn(game_id: str) -> None:
    _bought_this_turn[game_id] = False


def end_game_state(game_id: str) -> None:
    _bought_this_turn.pop(game_id, None)


def find_our_player(game: Game) -> Player | None:
    for player in game.players:
        if player.name == PLAYER_NAME:
            return player
    return None


def stock_quantity(stock: Cards, card_name: CardName) -> int:
    return stock.quantities.get(card_name, 0)


def hand_money(hand: Cards | None) -> int:
    if hand is None:
        return 0
    total = 0
    for card_name, quantity in hand.quantities.items():
        card_cls = Card.types.get(card_name)
        if card_cls is not None and card_cls.is_treasure:
            total += card_cls.money * quantity
    return total


def can_buy(game: Game, card_name: CardName) -> bool:
    return stock_quantity(game.stock, card_name) > 0


def choose_buy(game: Game, money: int) -> CardName | None:
    """Priorité Big Money : Province > Gold > Duchy (fin) > Silver."""
    provinces_left = stock_quantity(game.stock, CardName.PROVINCE)

    if money >= 8 and can_buy(game, CardName.PROVINCE):
        return CardName.PROVINCE
    if money >= 6 and can_buy(game, CardName.GOLD):
        return CardName.GOLD
    if (
        money >= 5
        and provinces_left <= PROVINCES_LEFT_FOR_DUCHY
        and can_buy(game, CardName.DUCHY)
    ):
        return CardName.DUCHY
    if money >= 3 and can_buy(game, CardName.SILVER):
        return CardName.SILVER
    return None


def decide_play(game: Game, game_id: str) -> str:
    """
    Décision pour POST /play.
    Phase 1 Big Money : pas d'action, un seul achat par tour, puis END_TURN.
    """
    if _bought_this_turn.get(game_id):
        return "END_TURN"

    player = find_our_player(game)
    if player is None:
        return "END_TURN"

    money = hand_money(player.hand)
    card = choose_buy(game, money)
    if card is None:
        return "END_TURN"

    _bought_this_turn[game_id] = True
    return f"BUY {card.value}"
