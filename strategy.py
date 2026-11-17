"""
Stratégie Chapelle-Big Money (visée top classement).

Socle : Province / Or / Argent + greening Duché/Gardens/Domaine.
Splash uniquement si utile :
- Chapelle×1 (dès 2$) — épure Domaines / Malédictions / Cuivres
- Sorcière×2, Milice×1
- Mine×1, Prêteur×1
- 1 Festival OU 1 village si plusieurs terminales
- Pas de Colonie, pas de Labo/Market/Hireling (ralentissent la course)

Toute exception dans decide_play → END_TURN.
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

# Empire green très tôt (beaucoup de Duchés / Domaines) : on aligne.
PROVINCES_LEFT_FOR_ESTATE = 4

CAPS: dict[CardName, int] = {
    CardName.WITCH: 2,
    CardName.MILITIA: 1,
    CardName.FESTIVAL: 1,
    CardName.VILLAGE: 1,
    CardName.FARMINGVILLAGE: 1,
    CardName.PORT: 1,
    CardName.SMITHY: 1,
    CardName.CHAPEL: 1,
    CardName.MINE: 1,
    CardName.MONEYLENDER: 1,
    CardName.REMODEL: 1,
    CardName.GARDENS: 4,
}


@dataclass
class TurnState:
    actions_left: int = 1
    purchases_left: int = 1
    money_spent: int = 0
    money_bonus: int = 0
    buy_phase: bool = False


@dataclass
class GameMemory:
    bought: dict[CardName, int] = field(default_factory=dict)
    turn: TurnState = field(default_factory=TurnState)
    provinces_left: int = 12
    curses_left: int = 20
    n_players: int = 2


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


def in_kingdom(game: Game, card_name: CardName) -> bool:
    return card_name in game.stock.quantities


def bought_count(mem: GameMemory, card_name: CardName) -> int:
    return mem.bought.get(card_name, 0)


def under_cap(mem: GameMemory, card_name: CardName) -> bool:
    cap = CAPS.get(card_name)
    if cap is None:
        return True
    return bought_count(mem, card_name) < cap


def approx_deck_size(mem: GameMemory) -> int:
    return 10 + sum(mem.bought.values())


def greening_thresholds(n_players: int) -> tuple[int, int, int]:
    """(duchy_at, gardens_at, stop_actions_at)."""
    if n_players <= 2:
        return 5, 6, 4
    if n_players == 3:
        return 9, 10, 5
    return 10, 11, 6


def village_count(mem: GameMemory) -> int:
    return (
        bought_count(mem, CardName.VILLAGE)
        + bought_count(mem, CardName.FARMINGVILLAGE)
        + bought_count(mem, CardName.PORT)
        + bought_count(mem, CardName.FESTIVAL)
    )


def terminal_count(mem: GameMemory) -> int:
    return (
        bought_count(mem, CardName.WITCH)
        + bought_count(mem, CardName.MILITIA)
        + bought_count(mem, CardName.SMITHY)
        + bought_count(mem, CardName.MINE)
        + bought_count(mem, CardName.MONEYLENDER)
        + bought_count(mem, CardName.REMODEL)
    )


def need_villages(mem: GameMemory) -> bool:
    """Village/Festival seulement si 2+ terminales à enchaîner."""
    return terminal_count(mem) >= 2 and village_count(mem) < 1


def action_overload(mem: GameMemory) -> bool:
    """Trop d'actions = deck lent : on repasse sur l'argent."""
    actions = terminal_count(mem) + village_count(mem)
    return actions >= 4


def _try(
    game: Game,
    mem: GameMemory,
    card: CardName,
    *,
    allow: bool = True,
) -> CardName | None:
    if not allow:
        return None
    if under_cap(mem, card) and can_buy(game, card):
        return card
    return None


def _want_gardens(mem: GameMemory, provinces_left: int, gardens_at: int) -> bool:
    if not under_cap(mem, CardName.GARDENS):
        return False
    if provinces_left <= gardens_at:
        return True
    if village_count(mem) > 0 and approx_deck_size(mem) >= 20:
        return True
    return approx_deck_size(mem) >= 28


def choose_buy(
    game: Game,
    money: int,
    mem: GameMemory,
    hand: Cards | None = None,
) -> CardName | None:
    del hand
    provinces_left = stock_quantity(game.stock, CardName.PROVINCE)
    n_players = max(2, len(game.players))
    mem.n_players = n_players
    duchy_at, gardens_at, stop_at = greening_thresholds(n_players)
    allow_actions = provinces_left > stop_at
    curses_left = stock_quantity(game.stock, CardName.CURSE)
    greening = provinces_left <= duchy_at
    want_gardens = _want_gardens(mem, provinces_left, gardens_at)
    witch_board = in_kingdom(game, CardName.WITCH)

    # --- Victoire / argent de haut niveau ---------------------------------
    # Pas de Colonie : les −10000 récents suivent presque toujours un BUY colony.
    if money >= 8 and can_buy(game, CardName.PROVINCE):
        return CardName.PROVINCE
    if money >= 9 and can_buy(game, CardName.PLATINUM):
        return CardName.PLATINUM

    if money >= 6 and can_buy(game, CardName.GOLD):
        return CardName.GOLD

    # Greening prioritaire dès que la course VP est lancée.
    if money >= 5 and provinces_left <= duchy_at and can_buy(game, CardName.DUCHY):
        return CardName.DUCHY

    if money >= 4 and want_gardens and can_buy(game, CardName.GARDENS):
        if greening or provinces_left <= gardens_at:
            return CardName.GARDENS

    buy_actions = allow_actions and not action_overload(mem)

    # --- Splash ciblé uniquement ------------------------------------------
    if buy_actions and money >= 5:
        if curses_left > 0 and (picked := _try(game, mem, CardName.WITCH)):
            return picked
        if picked := _try(game, mem, CardName.MINE):
            return picked
        # Festival = village + argent + achat : 1 max si 2 terminales.
        if need_villages(mem) and (picked := _try(game, mem, CardName.FESTIVAL)):
            return picked

    if buy_actions and money >= 4:
        if picked := _try(game, mem, CardName.MILITIA):
            return picked
        if need_villages(mem):
            for village in (
                CardName.FARMINGVILLAGE,
                CardName.PORT,
                CardName.VILLAGE,
            ):
                if picked := _try(game, mem, village):
                    return picked
        if picked := _try(game, mem, CardName.MONEYLENDER):
            return picked
        if bought_count(mem, CardName.WITCH) == 0:
            if picked := _try(game, mem, CardName.SMITHY):
                return picked
        if greening and (picked := _try(game, mem, CardName.REMODEL)):
            return picked

    if buy_actions and money >= 3:
        if need_villages(mem) and (picked := _try(game, mem, CardName.VILLAGE)):
            return picked

    # Chapelle dès 2–4$ : priorité absolue sur l'épuration.
    if buy_actions and money >= 2 and (picked := _try(game, mem, CardName.CHAPEL)):
        return picked

    if money >= 4 and want_gardens and can_buy(game, CardName.GARDENS):
        return CardName.GARDENS

    if money >= 3 and can_buy(game, CardName.SILVER):
        return CardName.SILVER

    if (
        money >= 2
        and provinces_left <= PROVINCES_LEFT_FOR_ESTATE
        and can_buy(game, CardName.ESTATE)
    ):
        return CardName.ESTATE

    if (
        money >= 2
        and money < 3
        and greening
        and village_count(mem) > 0
        and can_buy(game, CardName.ESTATE)
    ):
        return CardName.ESTATE

    return None


def _register_buy(mem: GameMemory, card: CardName) -> None:
    mem.bought[card] = bought_count(mem, card) + 1


def choose_action(hand: Cards | None, game: Game) -> CardName | None:
    if hand is None:
        return None

    # Chapelle si rebut en main (Domaines / Malédictions / Cuivres).
    if hand_quantity(hand, CardName.CHAPEL) > 0:
        junk = (
            hand_quantity(hand, CardName.CURSE)
            + hand_quantity(hand, CardName.COPPER)
            + hand_quantity(hand, CardName.ESTATE)
        )
        if junk > 0:
            return CardName.CHAPEL

    non_terminals: list[tuple[CardName, type[Card]]] = []
    terminals: list[tuple[CardName, type[Card]]] = []

    for card_name, qty in hand.quantities.items():
        if qty <= 0:
            continue
        card_cls = Card.types.get(card_name)
        if card_cls is None or not card_cls.is_action:
            continue
        if card_name == CardName.MONEYLENDER and hand_quantity(hand, CardName.COPPER) < 1:
            continue
        if card_name == CardName.MINE and (
            hand_quantity(hand, CardName.COPPER)
            + hand_quantity(hand, CardName.SILVER)
            + hand_quantity(hand, CardName.CURSEDGOLD)
        ) < 1:
            continue
        if card_name == CardName.CHAPEL:
            continue  # déjà géré ; sans rebut on ne la joue pas
        if card_cls.more_actions > 0:
            non_terminals.append((card_name, card_cls))
        else:
            terminals.append((card_name, card_cls))

    if non_terminals:
        non_terminals.sort(
            key=lambda item: (
                item[1].more_actions,
                item[1].more_purchases,
                item[1].more_money,
                item[1].more_cards_from_deck,
            ),
            reverse=True,
        )
        return non_terminals[0][0]

    if not terminals:
        return None

    curses_left = stock_quantity(game.stock, CardName.CURSE)
    has_copper = hand_quantity(hand, CardName.COPPER) > 0
    has_upgrade = (
        hand_quantity(hand, CardName.COPPER)
        + hand_quantity(hand, CardName.SILVER)
        + hand_quantity(hand, CardName.CURSEDGOLD)
    ) > 0

    def terminal_score(item: tuple[CardName, type[Card]]) -> tuple:
        name, cls = item
        if name == CardName.WITCH and curses_left > 0:
            prio = 50
        elif name == CardName.MONEYLENDER and has_copper:
            prio = 35
        elif name == CardName.MINE and has_upgrade:
            prio = 32
        elif name == CardName.MILITIA:
            prio = 25
        elif name == CardName.BANDIT:
            prio = 20
        elif name == CardName.REMODEL:
            prio = 15
        elif name == CardName.BUREAUCRAT:
            prio = 12
        elif name == CardName.WITCH:
            prio = 5
        else:
            prio = 0
        return (
            prio,
            cls.more_cards_from_deck,
            cls.more_purchases,
            cls.more_money,
        )

    terminals.sort(key=terminal_score, reverse=True)
    return terminals[0][0]


def _apply_action_effects(
    card: CardName,
    turn: TurnState,
    hand: Cards | None = None,
) -> None:
    turn.actions_left -= 1
    card_cls = Card.types.get(card)
    if card_cls is not None:
        turn.actions_left += card_cls.more_actions
        turn.purchases_left += card_cls.more_purchases
        turn.money_bonus += card_cls.more_money
    # Le Prêteur n'a pas more_money dans dopynion : +3$ si Cuivre écarté.
    if (
        card == CardName.MONEYLENDER
        and hand is not None
        and hand_quantity(hand, CardName.COPPER) > 0
    ):
        _consume_from_hand(hand, CardName.COPPER)
        turn.money_bonus += 3


def _consume_from_hand(hand: Cards, card: CardName) -> None:
    qty = hand.quantities.get(card, 0)
    if qty <= 1:
        hand.quantities.pop(card, None)
    else:
        hand.quantities[card] = qty - 1


# --- Hooks arbitre -------------------------------------------------------------


def _card_class(card: CardName) -> type[Card] | None:
    return Card.types.get(card)


def keep_value(card: CardName) -> int:
    if card == CardName.CURSE:
        return -1000
    cls = _card_class(card)
    if cls is None:
        return 0
    if cls.is_action:
        attack = {
            CardName.WITCH: 12,
            CardName.MILITIA: 10,
            CardName.BANDIT: 9,
            CardName.FESTIVAL: 8,
            CardName.LABORATORY: 8,
            CardName.HIRELING: 8,
            CardName.FARMINGVILLAGE: 7,
            CardName.PORT: 7,
            CardName.VILLAGE: 6,
            CardName.SMITHY: 5,
            CardName.MINE: 9,
            CardName.MONEYLENDER: 8,
            CardName.REMODEL: 6,
            CardName.CHAPEL: 11,
        }.get(card, 0)
        return (
            20
            + cls.more_cards_from_deck * 5
            + cls.more_actions * 4
            + cls.more_money * 3
            + cls.more_purchases * 2
            + attack
        )
    if cls.is_treasure:
        if card == CardName.COPPER:
            return 0
        return 50 + cls.money * 10
    if cls.is_victory:
        if card == CardName.GARDENS:
            return -40
        return -100 + cls.victory_points
    return 0


def gain_score(card: CardName, mem: GameMemory) -> int:
    if card == CardName.CURSE:
        return -1000
    duchy_at, gardens_at, _ = greening_thresholds(mem.n_players)
    late = mem.provinces_left <= duchy_at
    gardens_time = mem.provinces_left <= gardens_at
    endgame = mem.provinces_left <= PROVINCES_LEFT_FOR_ESTATE
    ranked = {
        CardName.COLONY: 200,
        CardName.PROVINCE: 190,
        CardName.PLATINUM: 170,
        CardName.GOLD: 160,
        CardName.WITCH: 155 if mem.curses_left > 0 else 25,
        CardName.HIRELING: 150,
        CardName.FESTIVAL: 145,
        CardName.LABORATORY: 142,
        CardName.MILITIA: 140,
        CardName.BANDIT: 138,
        CardName.MARKET: 130,
        CardName.FARMINGVILLAGE: 128,
        CardName.PORT: 126,
        CardName.VILLAGE: 124,
        CardName.SMITHY: 120,
        CardName.COUNCILROOM: 118,
        CardName.DUCHY: 110 if late else 28,
        CardName.GARDENS: 100 if gardens_time or approx_deck_size(mem) >= 20 else 40,
        CardName.MINE: 148,
        CardName.MONEYLENDER: 136,
        CardName.CHAPEL: 152,
        CardName.REMODEL: 90 if late else 55,
        CardName.SILVER: 80,
        CardName.ESTATE: 24 if endgame else 4,
        CardName.COPPER: 1,
        CardName.BUREAUCRAT: 50,
    }
    if card in ranked:
        return ranked[card]
    cls = _card_class(card)
    if cls is None:
        return 0
    return (
        cls.victory_points * 8
        + cls.money * 10
        + cls.more_cards_from_deck * 5
        + cls.more_actions * 4
        + cls.more_money * 3
    )


def _best_card(cards: list[CardName], score) -> CardName:
    return max(cards, key=score)


def confirm_discard(card: CardName, hand: list[CardName]) -> bool:
    del hand
    return keep_value(card) < 10


def confirm_trash(card: CardName, hand: list[CardName], mem: GameMemory) -> bool:
    del hand
    if card in (CardName.CURSE, CardName.COPPER):
        return True
    if card == CardName.ESTATE and mem.provinces_left > PROVINCES_LEFT_FOR_ESTATE:
        return True
    return card in (
        CardName.CHANCELLOR,
        CardName.WOODCUTTER,
        CardName.CELLAR,
        CardName.WORKSHOP,
    )


def choose_discard(hand: list[CardName]) -> CardName:
    return min(hand, key=keep_value)


def choose_trash(hand: list[CardName], mem: GameMemory) -> CardName:
    del mem

    def trash_rank(card: CardName) -> int:
        if card == CardName.CURSE:
            return 0
        if card == CardName.ESTATE:
            return 1
        if card == CardName.COPPER:
            return 2
        if card == CardName.SILVER:
            return 3
        if card == CardName.DUCHY:
            return 4
        if card == CardName.GARDENS:
            return 5
        if card == CardName.GOLD:
            return 7
        if card in (CardName.PROVINCE, CardName.COLONY):
            return 100
        return 50

    return min(hand, key=trash_rank)


def confirm_discard_deck() -> bool:
    return True


def choose_gain(cards: list[CardName], mem: GameMemory) -> CardName:
    return _best_card(cards, lambda card: gain_score(card, mem))


def skip_reception(card: CardName, hand: list[CardName]) -> bool:
    if card == CardName.CURSE:
        return True
    cls = _card_class(card)
    if cls is None:
        return True
    if cls.is_victory and not cls.is_action and not cls.is_treasure:
        return True
    if cls.is_treasure:
        return False
    if any(
        (other := _card_class(name)) is not None and other.is_action for name in hand
    ):
        return True
    return card in (
        CardName.CHANCELLOR,
        CardName.WOODCUTTER,
        CardName.CELLAR,
        CardName.WORKSHOP,
    )


def choose_money_to_upgrade(money_cards: list[CardName]) -> CardName:
    """Mine : Cuivre→Argent en priorité, sinon Argent→Or."""
    order = (
        CardName.COPPER,
        CardName.SILVER,
        CardName.CURSEDGOLD,
        CardName.GOLD,
        CardName.PLATINUM,
    )
    for card in order:
        if card in money_cards:
            return card
    return money_cards[0]


def _remember_stock(mem: GameMemory, game: Game) -> None:
    mem.provinces_left = stock_quantity(game.stock, CardName.PROVINCE)
    mem.curses_left = stock_quantity(game.stock, CardName.CURSE)
    mem.n_players = max(2, len(game.players))


def _decide_play_inner(game: Game, game_id: str) -> str:
    mem = _memory(game_id)
    _remember_stock(mem, game)
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
            _apply_action_effects(action, turn, player.hand)
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
    if money < 0:
        money = 0
    card = choose_buy(game, money, mem, player.hand)
    if card is None:
        turn.purchases_left = 0
        logger.info("game=%s money=%s -> END_TURN", game_id, money)
        return "END_TURN"

    cost = card_cost(card)
    if cost > money or not can_buy(game, card):
        # Sécurité : ne jamais proposer un achat invalide (élimination / −10000).
        turn.purchases_left = 0
        logger.warning(
            "game=%s refus achat invalide card=%s cost=%s money=%s",
            game_id,
            card,
            cost,
            money,
        )
        return "END_TURN"

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


def decide_play(game: Game, game_id: str) -> str:
    try:
        return _decide_play_inner(game, game_id)
    except Exception:
        logger.exception("game=%s decide_play crash -> END_TURN", game_id)
        try:
            mem = _memory(game_id)
            mem.turn.purchases_left = 0
            mem.turn.buy_phase = True
        except Exception:
            pass
        return "END_TURN"
