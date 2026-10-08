"""
Stratégie Big Money sûre pour Dopynion.

Aucune carte Action (évite les éliminations pour coup invalide).
Économie Silver → Gold → Province, avec Duchy/Estate seulement en fin de partie.
"""

from __future__ import annotations

import logging

from dopynion.cards import Card
from dopynion.data_model import CardName, Cards, Game, Player

logger = logging.getLogger("strategy")

PLAYER_NAME = "Groupe 5"
PROVINCES_LEFT_FOR_DUCHY = 5
PROVINCES_LEFT_FOR_ESTATE = 2

# game_id -> True si on a déjà effectué un achat ce tour
_bought_this_turn: dict[str, bool] = {}


def reset_turn(game_id: str) -> None:
    _bought_this_turn[game_id] = False


def end_game_state(game_id: str) -> None:
    _bought_this_turn.pop(game_id, None)


def find_our_player(game: Game) -> Player | None:
    """L'arbitre n'envoie la main que pour le joueur actif."""
    for player in game.players:
        if player.hand is not None:
            return player
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
    """
    1. Province ($8+)
    2. Gold ($6–7)
    3. Duchy ($5) si ≤ 5 Provinces restantes
    4. Silver ($3–5)
    5. Estate ($2) si ≤ 2 Provinces restantes
    """
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
    if (
        money >= 2
        and provinces_left <= PROVINCES_LEFT_FOR_ESTATE
        and can_buy(game, CardName.ESTATE)
    ):
        return CardName.ESTATE
    return None


def decide_play(game: Game, game_id: str) -> str:
    """Un seul BUY par tour, puis END_TURN. Aucune Action."""
    if _bought_this_turn.get(game_id):
        return "END_TURN"

    player = find_our_player(game)
    if player is None or player.hand is None:
        logger.warning(
            "game=%s aucun joueur avec main (names=%s)",
            game_id,
            [p.name for p in game.players],
        )
        return "END_TURN"

    money = hand_money(player.hand)
    card = choose_buy(game, money)
    if card is None:
        logger.info("game=%s money=%s -> END_TURN", game_id, money)
        return "END_TURN"

    _bought_this_turn[game_id] = True
    decision = f"BUY {card.value}"
    logger.info("game=%s money=%s -> %s", game_id, money, decision)
    return decision
