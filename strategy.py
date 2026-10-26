"""
Moteur Village / Forgeron + Big Money, avec cartes avancées.

Format arbitrage :
- action : ``ACTION <card>`` (ex. ``ACTION village``)
- achat  : ``BUY <card>``
- fin    : ``END_TURN``

Priorité d'achat (haut → bas) :
Province → Hireling → Gold → Duchy (≤5 Prov.) → Witch → Council Room
→ Farming Village → Smithy → Village → Silver → Estate (≤2 Prov.).
Les achats Action s'arrêtent quand il reste peu de Provinces.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

from dopynion.cards import Card
from dopynion.data_model import CardName, Cards, Game, Player

logger = logging.getLogger("strategy")

PLAYER_NAME = os.environ.get("PLAYER_NAME", "Groupe 5")

# Caps pour ne pas asphyxier le deck
MAX_HIRELING = 2
MAX_WITCH = 2
MAX_COUNCILROOM = 1
MAX_FARMINGVILLAGE = 2
MAX_SMITHY = 2
MAX_VILLAGE = 3

PROVINCES_LEFT_FOR_DUCHY = 5
PROVINCES_LEFT_FOR_ESTATE = 2
# Plus d'achats Action sous ce seuil de Provinces
PROVINCES_STOP_ACTIONS = 4

CARD_COST: dict[CardName, int] = {
    CardName.PROVINCE: 8,
    CardName.GOLD: 6,
    CardName.HIRELING: 6,
    CardName.DISTANTSHORE: 6,
    CardName.DUCHY: 5,
    CardName.WITCH: 5,
    CardName.COUNCILROOM: 5,
    CardName.FARMINGVILLAGE: 4,
    CardName.SMITHY: 4,
    CardName.VILLAGE: 3,
    CardName.SILVER: 3,
    CardName.ESTATE: 2,
}


@dataclass
class TurnState:
    actions_left: int = 1
    purchases_left: int = 1
    money_spent: int = 0
    buy_phase: bool = False


@dataclass
class GameMemory:
    hirelings_bought: int = 0
    witches_bought: int = 0
    councilrooms_bought: int = 0
    farmingvillages_bought: int = 0
    smithies_bought: int = 0
    villages_bought: int = 0
    turn: TurnState = field(default_factory=TurnState)


_games: dict[str, GameMemory] = {}
_lock = threading.Lock()


def _memory(game_id: str) -> GameMemory:
    with _lock:
        if game_id not in _games:
            _games[game_id] = GameMemory()
        return _games[game_id]


def init_game(game_id: str) -> None:
    """Nouvelle partie : mémoire isolée (parties simultanées)."""
    with _lock:
        _games[game_id] = GameMemory()


def reset_turn(game_id: str) -> None:
    mem = _memory(game_id)
    with _lock:
        mem.turn = TurnState()


def end_game_state(game_id: str) -> None:
    with _lock:
        _games.pop(game_id, None)


def find_our_player(game: Game) -> Player | None:
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


def actions_still_allowed(provinces_left: int) -> bool:
    return provinces_left > PROVINCES_STOP_ACTIONS


def choose_buy(
    game: Game,
    money: int,
    mem: GameMemory,
    hand: Cards | None = None,
) -> CardName | None:
    provinces_left = stock_quantity(game.stock, CardName.PROVINCE)
    allow_actions = actions_still_allowed(provinces_left)
    curses_left = stock_quantity(game.stock, CardName.CURSE)

    if money >= 8 and can_buy(game, CardName.PROVINCE):
        return CardName.PROVINCE

    if (
        money >= 6
        and allow_actions
        and mem.hirelings_bought < MAX_HIRELING
        and can_buy(game, CardName.HIRELING)
    ):
        return CardName.HIRELING

    if money >= 6 and can_buy(game, CardName.GOLD):
        return CardName.GOLD

    if (
        money >= 5
        and provinces_left <= PROVINCES_LEFT_FOR_DUCHY
        and can_buy(game, CardName.DUCHY)
    ):
        return CardName.DUCHY

    if (
        money >= 5
        and allow_actions
        and curses_left > 0
        and mem.witches_bought < MAX_WITCH
        and can_buy(game, CardName.WITCH)
    ):
        return CardName.WITCH

    if (
        money >= 5
        and allow_actions
        and mem.councilrooms_bought < MAX_COUNCILROOM
        and can_buy(game, CardName.COUNCILROOM)
    ):
        return CardName.COUNCILROOM

    if (
        money >= 4
        and allow_actions
        and mem.farmingvillages_bought < MAX_FARMINGVILLAGE
        and can_buy(game, CardName.FARMINGVILLAGE)
    ):
        return CardName.FARMINGVILLAGE

    if (
        money >= 4
        and allow_actions
        and mem.smithies_bought < MAX_SMITHY
        and can_buy(game, CardName.SMITHY)
    ):
        return CardName.SMITHY

    if (
        money >= 3
        and allow_actions
        and mem.villages_bought < MAX_VILLAGE
        and can_buy(game, CardName.VILLAGE)
    ):
        return CardName.VILLAGE

    if money >= 3 and can_buy(game, CardName.SILVER):
        return CardName.SILVER

    if (
        money >= 2
        and provinces_left <= PROVINCES_LEFT_FOR_ESTATE
        and can_buy(game, CardName.ESTATE)
    ):
        return CardName.ESTATE

    return None


def _register_buy(mem: GameMemory, card: CardName) -> None:
    if card == CardName.HIRELING:
        mem.hirelings_bought += 1
    elif card == CardName.WITCH:
        mem.witches_bought += 1
    elif card == CardName.COUNCILROOM:
        mem.councilrooms_bought += 1
    elif card == CardName.FARMINGVILLAGE:
        mem.farmingvillages_bought += 1
    elif card == CardName.SMITHY:
        mem.smithies_bought += 1
    elif card == CardName.VILLAGE:
        mem.villages_bought += 1


def choose_action(hand: Cards | None, game: Game) -> CardName | None:
    """Villages d'abord (moteur), puis terminaisons utiles."""
    if hand is None:
        return None

    # +actions : fluidifier avant les terminaisons
    if hand_quantity(hand, CardName.FARMINGVILLAGE) > 0:
        return CardName.FARMINGVILLAGE
    if hand_quantity(hand, CardName.VILLAGE) > 0:
        return CardName.VILLAGE
    if hand_quantity(hand, CardName.DISTANTSHORE) > 0:
        return CardName.DISTANTSHORE

    if hand_quantity(hand, CardName.HIRELING) > 0:
        return CardName.HIRELING

    if hand_quantity(hand, CardName.WITCH) > 0:
        return CardName.WITCH

    if hand_quantity(hand, CardName.COUNCILROOM) > 0:
        return CardName.COUNCILROOM

    if hand_quantity(hand, CardName.SMITHY) > 0:
        return CardName.SMITHY

    return None


def _apply_action_effects(card: CardName, turn: TurnState) -> None:
    turn.actions_left -= 1
    if card in (CardName.VILLAGE, CardName.FARMINGVILLAGE):
        turn.actions_left += 2
    elif card == CardName.DISTANTSHORE:
        turn.actions_left += 1
    elif card == CardName.COUNCILROOM:
        turn.purchases_left += 1


def _consume_from_hand(hand: Cards, card: CardName) -> None:
    qty = hand.quantities.get(card, 0)
    if qty <= 1:
        hand.quantities.pop(card, None)
    else:
        hand.quantities[card] = qty - 1


def decide_play(game: Game, game_id: str) -> str:
    mem = _memory(game_id)
    turn = mem.turn

    if turn.buy_phase and turn.purchases_left <= 0:
        return "END_TURN"

    player = find_our_player(game)
    if player is None or player.hand is None:
        logger.warning(
            "game=%s aucun joueur avec main (names=%s)",
            game_id,
            [p.name for p in game.players],
        )
        return "END_TURN"

    # Phase Action (plusieurs cartes possibles grâce aux Villages)
    if not turn.buy_phase and turn.actions_left > 0:
        action = choose_action(player.hand, game)
        if action is not None:
            _consume_from_hand(player.hand, action)
            _apply_action_effects(action, turn)
            decision = f"ACTION {action.value}"
            logger.info(
                "game=%s actions_left=%s -> %s",
                game_id,
                turn.actions_left,
                decision,
            )
            return decision
        turn.buy_phase = True

    if not turn.buy_phase:
        turn.buy_phase = True

    if turn.purchases_left <= 0:
        return "END_TURN"

    money = hand_money(player.hand) - turn.money_spent
    card = choose_buy(game, money, mem, player.hand)
    if card is None:
        turn.purchases_left = 0
        logger.info("game=%s money=%s -> END_TURN", game_id, money)
        return "END_TURN"

    cost = CARD_COST.get(card, 0)
    turn.money_spent += cost
    turn.purchases_left -= 1
    _register_buy(mem, card)

    decision = f"BUY {card.value}"
    logger.info(
        "game=%s money=%s spent=%s buys_left=%s -> %s",
        game_id,
        money,
        turn.money_spent,
        turn.purchases_left,
        decision,
    )
    return decision
