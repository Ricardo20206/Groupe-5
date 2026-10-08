"""
Stratégie Big Money+ pour Dopynion.

Meilleure que le Big Money pur pour gagner une vraie partie :
- même économie Silver → Gold → Province ;
- +1 Smithy si la carte est dans la réserve (pioche +3) ;
- Duchés / Estates seulement en fin de partie (ne dilue pas le deck tôt) ;
- une seule action puis un seul achat par tour → risque d'élimination bas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from dopynion.cards import Card
from dopynion.data_model import CardName, Cards, Game, Player

logger = logging.getLogger("strategy")

PLAYER_NAME = "Groupe 5"
MAX_SMITHY = 1
PROVINCES_LEFT_FOR_DUCHY = 5
PROVINCES_LEFT_FOR_ESTATE = 2


@dataclass
class TurnState:
    action_done: bool = False
    buy_done: bool = False


@dataclass
class GameMemory:
    smithies_bought: int = 0
    turns: dict[str, TurnState] = field(default_factory=dict)


_games: dict[str, GameMemory] = {}


def _memory(game_id: str) -> GameMemory:
    if game_id not in _games:
        _games[game_id] = GameMemory()
    return _games[game_id]


def reset_turn(game_id: str) -> None:
    _memory(game_id).turns[game_id] = TurnState()


def end_game_state(game_id: str) -> None:
    _games.pop(game_id, None)


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


def hand_quantity(hand: Cards | None, card_name: CardName) -> int:
    if hand is None:
        return 0
    return hand.quantities.get(card_name, 0)


def hand_money(hand: Cards | None) -> int:
    """Cuivre=1, Argent=2, Or=3 (et tout autre trésor via dopynion)."""
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


def smithy_owned(hand: Cards | None, mem: GameMemory) -> int:
    owned = mem.smithies_bought
    if hand_quantity(hand, CardName.SMITHY) > 0:
        owned = max(owned, 1)
    return owned


def choose_buy(
    game: Game,
    money: int,
    mem: GameMemory,
    hand: Cards | None = None,
) -> CardName | None:
    """
    Priorité Big Money+ :

    1. Province ($8+)
    2. Gold ($6–7)
    3. Duchy ($5) si ≤ 5 Provinces restantes
    4. Smithy ($4) une seule fois, seulement si pile non vide
    5. Silver ($3–5)
    6. Estate ($2) si ≤ 2 Provinces restantes
    Sinon rien (pas de Copper, pas d'Estate tôt).
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
    if (
        money >= 4
        and smithy_owned(hand, mem) < MAX_SMITHY
        and can_buy(game, CardName.SMITHY)
    ):
        return CardName.SMITHY
    if money >= 3 and can_buy(game, CardName.SILVER):
        return CardName.SILVER
    if (
        money >= 2
        and provinces_left <= PROVINCES_LEFT_FOR_ESTATE
        and can_buy(game, CardName.ESTATE)
    ):
        return CardName.ESTATE
    return None


def choose_action(hand: Cards | None) -> CardName | None:
    """Une seule action utile : Smithy, et seulement si elle est vraiment en main."""
    if hand is None:
        return None
    if hand_quantity(hand, CardName.SMITHY) > 0:
        return CardName.SMITHY
    return None


def decide_play(game: Game, game_id: str) -> str:
    """
    Ordre strict pour éviter les coups invalides :
    1) jouer Smithy si en main (phase Action)
    2) un seul BUY
    3) END_TURN
    """
    mem = _memory(game_id)
    turn = mem.turns.get(game_id)
    if turn is None:
        turn = TurnState()
        mem.turns[game_id] = turn

    if turn.buy_done:
        return "END_TURN"

    player = find_our_player(game)
    if player is None or player.hand is None:
        logger.warning(
            "game=%s aucun joueur avec main (names=%s)",
            game_id,
            [p.name for p in game.players],
        )
        return "END_TURN"

    if not turn.action_done:
        action = choose_action(player.hand)
        turn.action_done = True
        if action is not None:
            decision = action.value
            logger.info("game=%s -> ACTION %s", game_id, decision)
            return decision

    money = hand_money(player.hand)
    card = choose_buy(game, money, mem, player.hand)
    if card is None:
        turn.buy_done = True
        logger.info("game=%s money=%s -> END_TURN", game_id, money)
        return "END_TURN"

    turn.buy_done = True
    if card == CardName.SMITHY:
        mem.smithies_bought += 1

    decision = f"BUY {card.value}"
    logger.info("game=%s money=%s -> %s", game_id, money, decision)
    return decision
