"""
Stratégie adaptative au kingdom + Big Money.

Lit le stock : n'achète / ne joue que des cartes réellement disponibles.
Priorité économique : Province/Colony, Hireling, Platinum/Gold, puis les
meilleures Actions présentes (Witch, Lab, Festival, Market, Port, Smithy…).

Format : ``ACTION <card>`` / ``BUY <card>`` / ``END_TURN``.
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

PROVINCES_LEFT_FOR_DUCHY = 5
PROVINCES_LEFT_FOR_ESTATE = 2
PROVINCES_STOP_ACTIONS = 4

# Caps par type (évite d'asphyxier le deck)
CAPS: dict[CardName, int] = {
    CardName.HIRELING: 3,
    CardName.WITCH: 2,
    CardName.LABORATORY: 2,
    CardName.FESTIVAL: 2,
    CardName.MARKET: 2,
    CardName.COUNCILROOM: 1,
    CardName.BANDIT: 1,
    CardName.ARTIFICER: 1,
    CardName.PORT: 2,
    CardName.FARMINGVILLAGE: 2,
    CardName.MAGPIE: 2,
    CardName.SMITHY: 2,
    CardName.MILITIA: 1,
    CardName.MONEYLENDER: 1,
    CardName.VILLAGE: 3,
    CardName.WOODCUTTER: 1,
    CardName.DISTANTSHORE: 1,
}


@dataclass
class TurnState:
    actions_left: int = 1
    purchases_left: int = 1
    money_spent: int = 0
    money_bonus: int = 0  # +$ des Actions (Market, Festival…)
    buy_phase: bool = False


@dataclass
class GameMemory:
    bought: dict[CardName, int] = field(default_factory=dict)
    turn: TurnState = field(default_factory=TurnState)


_games: dict[str, GameMemory] = {}
_lock = threading.Lock()


def _memory(game_id: str) -> GameMemory:
    with _lock:
        if game_id not in _games:
            _games[game_id] = GameMemory()
        return _games[game_id]


def init_game(game_id: str) -> None:
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


def card_cost(card_name: CardName) -> int:
    card_cls = Card.types.get(card_name)
    return card_cls.cost if card_cls is not None else 99


def can_buy(game: Game, card_name: CardName) -> bool:
    return stock_quantity(game.stock, card_name) > 0


def bought_count(mem: GameMemory, card_name: CardName) -> int:
    return mem.bought.get(card_name, 0)


def under_cap(mem: GameMemory, card_name: CardName) -> bool:
    cap = CAPS.get(card_name)
    if cap is None:
        return True
    return bought_count(mem, card_name) < cap


def actions_still_allowed(provinces_left: int) -> bool:
    return provinces_left > PROVINCES_STOP_ACTIONS


def _try_action_buy(
    game: Game,
    mem: GameMemory,
    card: CardName,
    *,
    allow_actions: bool,
) -> CardName | None:
    if not allow_actions:
        return None
    if not under_cap(mem, card):
        return None
    if can_buy(game, card):
        return card
    return None


def choose_buy(
    game: Game,
    money: int,
    mem: GameMemory,
    hand: Cards | None = None,
) -> CardName | None:
    """Priorité adaptative : seules les piles non vides peuvent être choisies."""
    provinces_left = stock_quantity(game.stock, CardName.PROVINCE)
    allow_actions = actions_still_allowed(provinces_left)
    curses_left = stock_quantity(game.stock, CardName.CURSE)

    # Victoires / trésors haut de gamme
    if money >= 11 and can_buy(game, CardName.COLONY):
        return CardName.COLONY
    if money >= 8 and can_buy(game, CardName.PROVINCE):
        return CardName.PROVINCE
    if money >= 9 and can_buy(game, CardName.PLATINUM):
        return CardName.PLATINUM

    if money >= 6:
        picked = _try_action_buy(game, mem, CardName.HIRELING, allow_actions=allow_actions)
        if picked:
            return picked
        if can_buy(game, CardName.GOLD):
            return CardName.GOLD

    if (
        money >= 5
        and provinces_left <= PROVINCES_LEFT_FOR_DUCHY
        and can_buy(game, CardName.DUCHY)
    ):
        return CardName.DUCHY

    if money >= 5:
        if curses_left > 0:
            picked = _try_action_buy(game, mem, CardName.WITCH, allow_actions=allow_actions)
            if picked:
                return picked
        for card in (
            CardName.LABORATORY,
            CardName.FESTIVAL,
            CardName.MARKET,
            CardName.BANDIT,
            CardName.COUNCILROOM,
            CardName.ARTIFICER,
        ):
            picked = _try_action_buy(game, mem, card, allow_actions=allow_actions)
            if picked:
                return picked

    if money >= 4:
        for card in (
            CardName.PORT,
            CardName.FARMINGVILLAGE,
            CardName.MAGPIE,
            CardName.SMITHY,
            CardName.MILITIA,
        ):
            picked = _try_action_buy(game, mem, card, allow_actions=allow_actions)
            if picked:
                return picked
        picked = _try_action_buy(
            game, mem, CardName.MONEYLENDER, allow_actions=allow_actions
        )
        if picked:
            return picked

    if money >= 3:
        picked = _try_action_buy(game, mem, CardName.VILLAGE, allow_actions=allow_actions)
        if picked:
            return picked
        picked = _try_action_buy(
            game, mem, CardName.WOODCUTTER, allow_actions=allow_actions
        )
        if picked:
            return picked
        if can_buy(game, CardName.SILVER):
            return CardName.SILVER

    if (
        money >= 2
        and provinces_left <= PROVINCES_LEFT_FOR_ESTATE
        and can_buy(game, CardName.ESTATE)
    ):
        return CardName.ESTATE

    return None


def _register_buy(mem: GameMemory, card: CardName) -> None:
    mem.bought[card] = bought_count(mem, card) + 1


def choose_action(hand: Cards | None, game: Game) -> CardName | None:
    """Joue d'abord les +Actions, puis Hireling, puis le reste."""
    if hand is None:
        return None

    non_terminals: list[tuple[CardName, type[Card]]] = []
    terminals: list[tuple[CardName, type[Card]]] = []

    for card_name, qty in hand.quantities.items():
        if qty <= 0:
            continue
        card_cls = Card.types.get(card_name)
        if card_cls is None or not card_cls.is_action:
            continue
        # MoneyLender seulement si Copper en main
        if card_name == CardName.MONEYLENDER and hand_quantity(hand, CardName.COPPER) < 1:
            continue
        if card_cls.more_actions > 0:
            non_terminals.append((card_name, card_cls))
        else:
            terminals.append((card_name, card_cls))

    if non_terminals:
        non_terminals.sort(
            key=lambda item: (
                item[1].more_actions,
                item[1].more_cards_from_deck,
                item[1].more_purchases,
                item[1].more_money,
            ),
            reverse=True,
        )
        return non_terminals[0][0]

    if hand_quantity(hand, CardName.HIRELING) > 0:
        return CardName.HIRELING

    if not terminals:
        return None

    curses_left = stock_quantity(game.stock, CardName.CURSE)

    def terminal_score(item: tuple[CardName, type[Card]]) -> tuple:
        name, cls = item
        witch_bonus = 1 if name == CardName.WITCH and curses_left > 0 else 0
        return (
            witch_bonus,
            cls.more_cards_from_deck,
            cls.more_purchases,
            cls.more_money,
        )

    terminals.sort(key=terminal_score, reverse=True)
    return terminals[0][0]


def _apply_action_effects(card: CardName, turn: TurnState) -> None:
    turn.actions_left -= 1
    card_cls = Card.types.get(card)
    if card_cls is None:
        return
    turn.actions_left += card_cls.more_actions
    turn.purchases_left += card_cls.more_purchases
    turn.money_bonus += card_cls.more_money


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

    if not turn.buy_phase and turn.actions_left > 0:
        action = choose_action(player.hand, game)
        if action is not None:
            _consume_from_hand(player.hand, action)
            _apply_action_effects(action, turn)
            decision = f"ACTION {action.value}"
            logger.info(
                "game=%s actions_left=%s money_bonus=%s -> %s",
                game_id,
                turn.actions_left,
                turn.money_bonus,
                decision,
            )
            return decision
        turn.buy_phase = True

    if not turn.buy_phase:
        turn.buy_phase = True

    if turn.purchases_left <= 0:
        return "END_TURN"

    money = hand_money(player.hand) + turn.money_bonus - turn.money_spent
    card = choose_buy(game, money, mem, player.hand)
    if card is None:
        turn.purchases_left = 0
        logger.info("game=%s money=%s -> END_TURN", game_id, money)
        return "END_TURN"

    cost = card_cost(card)
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
