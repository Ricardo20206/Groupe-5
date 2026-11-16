"""
Stratégie adaptative : 3 plans selon le kingdom.

- WITCH : Chapelle → Village → Sorcière(s) → Or → Provinces
- ATTACK : 1 Bandit ou 1 Milice max, beaucoup d'Or, greening agressif
- ENGINE : Labo / Festival / Marché / Port, presque zéro attaque
- BIG_MONEY : Argent / Or / Province si le kingdom est pauvre

Greening selon le nombre de joueurs (8 Provinces en 2j, 12 en 3–4j).
Village/Port avant une 2e terminale. Pas de Chambre du conseil, Bureaucrate ni Jardin.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from enum import StrEnum

from dopynion.cards import Card
from dopynion.data_model import CardName, Cards, Game, Player

logger = logging.getLogger("strategy")

PLAYER_NAME = os.environ.get("PLAYER_NAME", "Groupe 5")

PROVINCES_LEFT_FOR_ESTATE = 2

# Caps par type (évite d'asphyxier le deck)
CAPS: dict[CardName, int] = {
    CardName.HIRELING: 3,
    CardName.WITCH: 2,
    CardName.CHAPEL: 1,
    CardName.LABORATORY: 2,
    CardName.FESTIVAL: 2,
    CardName.MARKET: 2,
    CardName.BANDIT: 1,
    CardName.MILITIA: 1,
    CardName.ARTIFICER: 1,
    CardName.PORT: 2,
    CardName.FARMINGVILLAGE: 2,
    CardName.MAGPIE: 2,
    CardName.SMITHY: 2,
    CardName.MONEYLENDER: 1,
    CardName.VILLAGE: 3,
    CardName.WOODCUTTER: 1,
    CardName.DISTANTSHORE: 1,
}

TERMINALS = frozenset({
    CardName.WITCH,
    CardName.BANDIT,
    CardName.MILITIA,
    CardName.SMITHY,
    CardName.MONEYLENDER,
    CardName.WOODCUTTER,
    CardName.CHAPEL,
})

ENGINES = frozenset({
    CardName.VILLAGE,
    CardName.PORT,
    CardName.FARMINGVILLAGE,
    CardName.MARKET,
    CardName.LABORATORY,
    CardName.FESTIVAL,
    CardName.MAGPIE,
})

ENGINE_SIGNAL = (
    CardName.LABORATORY,
    CardName.FESTIVAL,
    CardName.MARKET,
    CardName.PORT,
    CardName.FARMINGVILLAGE,
    CardName.VILLAGE,
    CardName.MAGPIE,
)


class Plan(StrEnum):
    WITCH = "witch"
    ATTACK = "attack"
    ENGINE = "engine"
    BIG_MONEY = "big_money"


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
    provinces_left: int = 12
    curses_left: int = 20
    n_players: int = 2
    plan: Plan = Plan.BIG_MONEY


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


def greening_thresholds(n_players: int) -> tuple[int, int]:
    """(duchy_at_or_below, stop_actions_at_or_below).

    2 joueurs : pile de 8 Provinces → fin rapide, greening agressif.
    3–4 joueurs : pile de 12 → greening selon la vitesse de la table.
    """
    if n_players <= 2:
        return 6, 5
    if n_players == 3:
        return 6, 5
    return 7, 6


def actions_still_allowed(provinces_left: int, n_players: int = 2) -> bool:
    _, stop_at = greening_thresholds(n_players)
    return provinces_left > stop_at


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


def _present(game: Game, mem: GameMemory, card: CardName) -> bool:
    return stock_quantity(game.stock, card) > 0 or bought_count(mem, card) > 0


def _witch_in_kingdom(game: Game, mem: GameMemory) -> bool:
    return _present(game, mem, CardName.WITCH)


def _terminal_bought(mem: GameMemory) -> int:
    return sum(bought_count(mem, card) for card in TERMINALS)


def _engine_bought(mem: GameMemory) -> int:
    return sum(bought_count(mem, card) for card in ENGINES)


def _needs_engine(mem: GameMemory) -> bool:
    """True si une terminale de plus noierait le deck sans Village/Port."""
    return _terminal_bought(mem) > _engine_bought(mem)


def _engine_signal_count(game: Game, mem: GameMemory) -> int:
    return sum(1 for card in ENGINE_SIGNAL if _present(game, mem, card))


def _strong_engine(game: Game, mem: GameMemory) -> bool:
    if _present(game, mem, CardName.LABORATORY):
        return True
    if _present(game, mem, CardName.FESTIVAL):
        return True
    has_market = _present(game, mem, CardName.MARKET)
    has_village = (
        _present(game, mem, CardName.VILLAGE)
        or _present(game, mem, CardName.PORT)
        or _present(game, mem, CardName.FARMINGVILLAGE)
    )
    return has_market and has_village


def detect_plan(game: Game, mem: GameMemory) -> Plan:
    """Choisit le plan selon les piles réellement présentes."""
    curses_left = stock_quantity(game.stock, CardName.CURSE)
    if _witch_in_kingdom(game, mem) and (
        curses_left > 0 or bought_count(mem, CardName.WITCH) > 0
    ):
        return Plan.WITCH

    if _engine_signal_count(game, mem) >= 3 and _strong_engine(game, mem):
        return Plan.ENGINE

    if (
        _present(game, mem, CardName.BANDIT)
        or _present(game, mem, CardName.MILITIA)
    ):
        return Plan.ATTACK

    if _engine_signal_count(game, mem) >= 2:
        return Plan.ENGINE
    return Plan.BIG_MONEY


def _try_engine_buy(
    game: Game,
    mem: GameMemory,
    *,
    allow_actions: bool,
    money: int,
) -> CardName | None:
    if money >= 5:
        for card in (CardName.LABORATORY, CardName.FESTIVAL, CardName.MARKET):
            picked = _try_action_buy(game, mem, card, allow_actions=allow_actions)
            if picked:
                return picked
    if money >= 4:
        for card in (CardName.PORT, CardName.FARMINGVILLAGE, CardName.MAGPIE):
            picked = _try_action_buy(game, mem, card, allow_actions=allow_actions)
            if picked:
                return picked
        if mem.plan == Plan.ENGINE:
            picked = _try_action_buy(game, mem, CardName.SMITHY, allow_actions=allow_actions)
            if picked:
                return picked
    if money >= 3:
        picked = _try_action_buy(game, mem, CardName.VILLAGE, allow_actions=allow_actions)
        if picked:
            return picked
    return None


def _can_buy_witch(game: Game, mem: GameMemory) -> bool:
    """2e Sorcière seulement si on a déjà un Village/Port/moteur."""
    have = bought_count(mem, CardName.WITCH)
    if have >= 2:
        return False
    if have >= 1 and _engine_bought(mem) < 1:
        return False
    return under_cap(mem, CardName.WITCH) and can_buy(game, CardName.WITCH)


def _attack_bought(mem: GameMemory) -> int:
    return (
        bought_count(mem, CardName.BANDIT)
        + bought_count(mem, CardName.MILITIA)
        + bought_count(mem, CardName.WITCH)
    )


def _prefer_attack(
    game: Game,
    mem: GameMemory,
    curses_left: int,
) -> CardName | None:
    """Selon le plan : Sorcière, ou 1 seule attaque légère."""
    if mem.plan == Plan.ENGINE:
        return None
    if _needs_engine(mem):
        return None
    if mem.plan == Plan.ATTACK and _attack_bought(mem) >= 1:
        return None

    if mem.plan == Plan.WITCH and curses_left > 0 and _can_buy_witch(game, mem):
        return CardName.WITCH

    if mem.plan in (Plan.ATTACK, Plan.WITCH) and curses_left <= 0:
        picked = _try_action_buy(game, mem, CardName.BANDIT, allow_actions=True)
        if picked:
            return picked

    if mem.plan == Plan.ATTACK:
        picked = _try_action_buy(game, mem, CardName.BANDIT, allow_actions=True)
        if picked:
            return picked
        return _try_action_buy(game, mem, CardName.MILITIA, allow_actions=True)

    if mem.plan == Plan.WITCH and curses_left > 0:
        return None

    return _try_action_buy(game, mem, CardName.BANDIT, allow_actions=True)


def _buy_high_vp(game: Game, money: int) -> CardName | None:
    if money >= 11 and can_buy(game, CardName.COLONY):
        return CardName.COLONY
    if money >= 8 and can_buy(game, CardName.PROVINCE):
        return CardName.PROVINCE
    if money >= 9 and can_buy(game, CardName.PLATINUM):
        return CardName.PLATINUM
    return None


def choose_buy(
    game: Game,
    money: int,
    mem: GameMemory,
    hand: Cards | None = None,
) -> CardName | None:
    """Priorité adaptative : plan kingdom + greening selon le nombre de joueurs."""
    del hand
    provinces_left = stock_quantity(game.stock, CardName.PROVINCE)
    n_players = max(2, len(game.players))
    mem.n_players = n_players
    mem.plan = detect_plan(game, mem)
    duchy_at, stop_at = greening_thresholds(n_players)
    allow_actions = provinces_left > stop_at
    curses_left = stock_quantity(game.stock, CardName.CURSE)

    high = _buy_high_vp(game, money)
    if high is not None:
        return high

    # Plan ENGINE : moteur avant attaque / Or
    if mem.plan == Plan.ENGINE and money >= 5 and allow_actions:
        if _needs_engine(mem) or _engine_bought(mem) < 2:
            picked = _try_engine_buy(game, mem, allow_actions=True, money=money)
            if picked:
                return picked

    if money >= 6 and allow_actions:
        if _needs_engine(mem):
            picked = _try_engine_buy(game, mem, allow_actions=True, money=money)
            if picked:
                return picked
        if mem.plan != Plan.ENGINE:
            picked = _prefer_attack(game, mem, curses_left)
            if picked:
                return picked
        picked = _try_action_buy(game, mem, CardName.HIRELING, allow_actions=True)
        if picked:
            return picked

    if money >= 6 and can_buy(game, CardName.GOLD):
        return CardName.GOLD

    if money >= 5 and provinces_left <= duchy_at and can_buy(game, CardName.DUCHY):
        return CardName.DUCHY

    if money >= 5 and allow_actions:
        if _needs_engine(mem) or mem.plan == Plan.ENGINE:
            picked = _try_engine_buy(game, mem, allow_actions=True, money=money)
            if picked:
                return picked
        if mem.plan != Plan.ENGINE:
            picked = _prefer_attack(game, mem, curses_left)
            if picked:
                return picked
        for card in (
            CardName.LABORATORY,
            CardName.FESTIVAL,
            CardName.MARKET,
            CardName.ARTIFICER,
        ):
            picked = _try_action_buy(game, mem, card, allow_actions=True)
            if picked:
                return picked

    if money >= 4 and allow_actions:
        if _needs_engine(mem) or mem.plan == Plan.ENGINE:
            picked = _try_engine_buy(game, mem, allow_actions=True, money=money)
            if picked:
                return picked
        if mem.plan == Plan.ATTACK and not _needs_engine(mem):
            picked = _prefer_attack(game, mem, curses_left)
            if picked and picked == CardName.MILITIA:
                return picked
            picked = _try_action_buy(game, mem, CardName.MILITIA, allow_actions=True)
            if picked and _attack_bought(mem) < 1:
                return picked
        for card in (CardName.PORT, CardName.FARMINGVILLAGE, CardName.MAGPIE):
            picked = _try_action_buy(game, mem, card, allow_actions=True)
            if picked:
                return picked
        if mem.plan == Plan.WITCH and bought_count(mem, CardName.CHAPEL) == 0:
            picked = _try_action_buy(
                game, mem, CardName.MONEYLENDER, allow_actions=True
            )
            if picked:
                return picked
        if mem.plan != Plan.ENGINE and not _needs_engine(mem):
            for card in (CardName.SMITHY, CardName.MONEYLENDER):
                picked = _try_action_buy(game, mem, card, allow_actions=True)
                if picked:
                    return picked
        if mem.plan == Plan.ENGINE and not _needs_engine(mem):
            picked = _try_action_buy(game, mem, CardName.SMITHY, allow_actions=True)
            if picked:
                return picked

    # Chapelle tôt uniquement en plan Sorcière
    if (
        money < 4
        and mem.plan == Plan.WITCH
        and allow_actions
    ):
        picked = _try_action_buy(game, mem, CardName.CHAPEL, allow_actions=True)
        if picked:
            return picked

    if money >= 3:
        if allow_actions and (_needs_engine(mem) or mem.plan in (Plan.ENGINE, Plan.WITCH)):
            picked = _try_engine_buy(game, mem, allow_actions=True, money=money)
            if picked:
                return picked
        picked = _try_action_buy(game, mem, CardName.VILLAGE, allow_actions=allow_actions)
        if picked:
            return picked
        if allow_actions and mem.plan != Plan.ENGINE and not _needs_engine(mem):
            picked = _try_action_buy(
                game, mem, CardName.WOODCUTTER, allow_actions=True
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


def _chapel_trash_targets(hand: Cards, provinces_left: int) -> int:
    """Combien de cartes la Chapelle peut utilement écarter dans cette main."""
    total = 0
    for card_name, qty in hand.quantities.items():
        if qty <= 0:
            continue
        if card_name == CardName.CHAPEL:
            continue
        if card_name in (CardName.CURSE, CardName.COPPER):
            total += qty
        elif (
            card_name == CardName.ESTATE
            and provinces_left > PROVINCES_LEFT_FOR_ESTATE
        ):
            total += qty
        elif card_name in (
            CardName.CHANCELLOR,
            CardName.WOODCUTTER,
            CardName.CELLAR,
            CardName.WORKSHOP,
        ):
            total += qty
    return total


def choose_action(hand: Cards | None, game: Game) -> CardName | None:
    """Joue +Actions, puis Chapelle s'il y a du rebut, puis Hireling, puis attaques."""
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

    provinces_left = stock_quantity(game.stock, CardName.PROVINCE)
    if (
        hand_quantity(hand, CardName.CHAPEL) > 0
        and _chapel_trash_targets(hand, provinces_left) > 0
    ):
        return CardName.CHAPEL

    if hand_quantity(hand, CardName.HIRELING) > 0:
        return CardName.HIRELING

    if not terminals:
        return None

    curses_left = stock_quantity(game.stock, CardName.CURSE)
    attack_rank = {
        CardName.WITCH: 4 if curses_left > 0 else 0,
        CardName.BANDIT: 3,
        CardName.MILITIA: 2,
    }

    def terminal_score(item: tuple[CardName, type[Card]]) -> tuple:
        name, cls = item
        return (
            attack_rank.get(name, 0),
            cls.more_cards_from_deck,
            cls.more_purchases,
            cls.more_money,
            1 if name == CardName.BUREAUCRAT else 0,
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


# --- Décisions imposées par l'arbitre (hooks) ---------------------------------


def _card_class(card: CardName) -> type[Card] | None:
    return Card.types.get(card)


def keep_value(card: CardName) -> int:
    """Plus le score est haut, plus on garde la carte en main."""
    if card == CardName.CURSE:
        return -1000
    cls = _card_class(card)
    if cls is None:
        return 0
    if cls.is_action:
        attack = {
            CardName.WITCH: 8,
            CardName.BANDIT: 7,
            CardName.MILITIA: 6,
            CardName.BUREAUCRAT: 3,
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
        return -100 + cls.victory_points
    return 0


def gain_score(card: CardName, mem: GameMemory) -> int:
    """Plus le score est haut, plus on veut recevoir la carte."""
    if card == CardName.CURSE:
        return -1000
    if card == CardName.WITCH and mem.curses_left <= 0:
        return 15
    duchy_at, _ = greening_thresholds(mem.n_players)
    late = mem.provinces_left <= duchy_at
    endgame = mem.provinces_left <= PROVINCES_LEFT_FOR_ESTATE
    engine_bias = 20 if mem.plan == Plan.ENGINE else 0
    witch_bias = 20 if mem.plan == Plan.WITCH else 0
    ranked = {
        CardName.COLONY: 200,
        CardName.PROVINCE: 190,
        CardName.PLATINUM: 170,
        CardName.GOLD: 160,
        CardName.WITCH: 155 + witch_bias,
        CardName.BANDIT: 150 if mem.plan != Plan.ENGINE else 40,
        CardName.HIRELING: 145,
        CardName.LABORATORY: 140 + engine_bias,
        CardName.FESTIVAL: 138 + engine_bias,
        CardName.MARKET: 136 + engine_bias,
        CardName.MILITIA: 134 if mem.plan == Plan.ATTACK else 50,
        CardName.BUREAUCRAT: 40,
        CardName.COUNCILROOM: 30,
        CardName.SMITHY: 120 + engine_bias // 2,
        CardName.PORT: 118 + engine_bias,
        CardName.FARMINGVILLAGE: 116 + engine_bias,
        CardName.MAGPIE: 112 + engine_bias,
        CardName.VILLAGE: 108 + engine_bias + witch_bias // 2,
        CardName.CHAPEL: 100 if mem.plan == Plan.WITCH else 20,
        CardName.DUCHY: 110 if late else 28,
        CardName.SILVER: 80,
        CardName.MONEYLENDER: 70,
        CardName.GARDENS: 20,
        CardName.WOODCUTTER: 34,
        CardName.CHANCELLOR: 30,
        CardName.ESTATE: 24 if endgame else 4,
        CardName.COPPER: 1,
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
    """Défausse volontaire (Cave, Artificier) : rebut, victoires mortes, Cuivre."""
    del hand
    return keep_value(card) < 10


def confirm_trash(card: CardName, hand: list[CardName], mem: GameMemory) -> bool:
    """Écart définitif : Malédiction, Cuivre, Domaine tôt, actions faibles."""
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
    """Milice / Braconnier : on lâche d'abord la carte la moins utile."""
    return min(hand, key=keep_value)


def choose_trash(hand: list[CardName], mem: GameMemory) -> CardName:
    """Rénovation (+2) et Renouvellement (+1) : améliorer un rebut, pas une Province."""
    del mem

    def trash_rank(card: CardName) -> int:
        if card == CardName.CURSE:
            return 0
        if card == CardName.ESTATE:
            return 1
        if card == CardName.SILVER:
            return 2
        if card == CardName.COPPER:
            return 3
        if card == CardName.DUCHY:
            return 4
        if card == CardName.GARDENS:
            return 5
        if card in (
            CardName.CHANCELLOR,
            CardName.WOODCUTTER,
            CardName.CELLAR,
            CardName.WORKSHOP,
        ):
            return 6
        if card == CardName.GOLD:
            return 7
        if card in (CardName.PROVINCE, CardName.COLONY):
            return 100
        return 50

    return min(hand, key=trash_rank)


def confirm_discard_deck() -> bool:
    """Chancelier : défausser la pioche accélère le mélange."""
    return True


def choose_gain(cards: list[CardName], mem: GameMemory) -> CardName:
    return _best_card(cards, lambda card: gain_score(card, mem))


def skip_reception(card: CardName, hand: list[CardName]) -> bool:
    """Bibliothèque : True = refuser la carte. On prend trésors et une action."""
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
    """Mine : Argent→Or d'abord, puis Cuivre→Argent, Or en dernier."""
    order = (
        CardName.SILVER,
        CardName.COPPER,
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
    mem.plan = detect_plan(game, mem)


def decide_play(game: Game, game_id: str) -> str:
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
            _apply_action_effects(action, turn)
            decision = f"ACTION {action.value}"
            logger.info(
                "game=%s plan=%s actions_left=%s money_bonus=%s -> %s",
                game_id,
                mem.plan,
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
        logger.info("game=%s plan=%s money=%s -> END_TURN", game_id, mem.plan, money)
        return "END_TURN"

    cost = card_cost(card)
    turn.money_spent += cost
    turn.purchases_left -= 1
    _register_buy(mem, card)

    decision = f"BUY {card.value}"
    logger.info(
        "game=%s plan=%s money=%s spent=%s buys_left=%s -> %s",
        game_id,
        mem.plan,
        money,
        turn.money_spent,
        turn.purchases_left,
        decision,
    )
    return decision
