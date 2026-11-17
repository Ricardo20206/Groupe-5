"""
Arbitre local dopynion — scores EXACTS des parties jouées (pas d'estimation Elo).

Exemple :
  python local_arbiter.py
  python local_arbiter.py --games 80 --players 2
  python local_arbiter.py --games 80 --players 3
"""

from __future__ import annotations

import argparse
import random
import time
import uuid
from pathlib import Path
from typing import Callable

from dopynion.cards import Card, CardName
from dopynion.data_model import CardNameAndHand, Hand, MoneyCardsInHand, PossibleCards
from dopynion.game import Game
from dopynion.player import DefaultPlayerHooks, Player, PlayerHooks
from dopynion import record as dopynion_record

import strategy as strat

_BENCH_DIR = Path(__file__).resolve().parent / "games_bench"
_BENCH_DIR.mkdir(exist_ok=True)
dopynion_record.records_dir = _BENCH_DIR


def _silence_records() -> None:
    class QuietRecord:
        def __init__(self) -> None:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            from dopynion.data_model import Cards, GameRecord

            self._file = _BENCH_DIR / "_quiet.dop"
            self._game_record = GameRecord(
                date=datetime.now(tz=ZoneInfo("Europe/Paris")),
                stock=Cards(),
            )

        def save(self, game) -> Path:  # noqa: ANN001, ARG002
            return self._file

        def start_turn(self) -> None:
            from dopynion.data_model import PlayerTurnRecord

            self._game_record.turns.append(PlayerTurnRecord())

        def add_stock(self, stock) -> None:  # noqa: ANN001
            self._game_record.stock = stock

        def add_action(self, action: str, player: Player) -> None:  # noqa: ARG002
            return

        def add_error(self, error: str, player: Player) -> None:  # noqa: ARG002
            return

        def add_warning(self, error: str, player: Player) -> None:  # noqa: ARG002
            return

        def add_hook_call(self, player, name, args) -> None:  # noqa: ANN001, ARG002
            return

        def add_hook_result(self, player, result) -> None:  # noqa: ANN001, ARG002
            return

    dopynion_record.Record = QuietRecord  # type: ignore[misc, assignment]


_silence_records()


class StrategyHooks(PlayerHooks):
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id

    def _mem(self) -> strat.GameMemory:
        return strat._memory(self.game_id)

    def confirm_discard_card_from_hand(self, decision_input: CardNameAndHand) -> bool:
        return strat.confirm_discard(decision_input.card_name, decision_input.hand)

    def confirm_trash_card_from_hand(self, decision_input: CardNameAndHand) -> bool:
        return strat.confirm_trash(
            decision_input.card_name,
            decision_input.hand,
            self._mem(),
        )

    def discard_card_from_hand(self, decision_input: Hand) -> CardName:
        return strat.choose_discard(decision_input.hand)

    def trash_card_from_hand(self, decision_input: Hand) -> CardName:
        return strat.choose_trash(decision_input.hand, self._mem())

    def confirm_discard_deck(self) -> bool:
        return strat.confirm_discard_deck()

    def choose_card_to_receive_in_discard(self, decision_input: PossibleCards) -> CardName:
        return strat.choose_gain(decision_input.possible_cards, self._mem())

    def choose_card_to_receive_in_deck(self, decision_input: PossibleCards) -> CardName:
        return strat.choose_gain(decision_input.possible_cards, self._mem())

    def skip_card_reception_in_hand(self, decision_input: CardNameAndHand) -> bool:
        return strat.skip_reception(decision_input.card_name, decision_input.hand)

    def trash_money_card_for_better_money_card(
        self,
        decision_input: MoneyCardsInHand,
    ) -> CardName | None:
        if not decision_input.money_in_hand:
            return None
        return strat.choose_money_to_upgrade(decision_input.money_in_hand)


def play_strategy_turn(player: Player, game_id: str) -> None:
    mem = strat._memory(game_id)
    player.start_turn()

    safety = 0
    while player.actions_left > 0 and player.hand.contains_action() and safety < 30:
        safety += 1
        card = strat.choose_action(player.hand.state, player.game.state)
        if card is None:
            break
        try:
            player.action(card)
        except Exception:
            break

    safety = 0
    while player.purchases_left > 0 and safety < 20:
        safety += 1
        money = player.money + player.hand.money
        if money <= 0 and not player.hand.contains_money():
            break
        card = strat.choose_buy(player.game.state, money, mem, player.hand.state)
        if card is None:
            break
        try:
            player.buy(card)
            strat._register_buy(mem, card)
        except Exception:
            break

    player.end_turn()


def play_big_money_turn(player: Player) -> None:
    player.start_turn()
    safety = 0
    while player.actions_left > 0 and player.hand.contains_action() and safety < 20:
        safety += 1
        actions = [c for c in player.hand if Card.class_(c).is_action]
        if not actions:
            break

        def score(c: CardName) -> tuple:
            cls = Card.class_(c)
            if c == CardName.MONEYLENDER and CardName.COPPER not in player.hand:
                return (-1, 0)
            return (cls.more_actions, cls.more_cards_from_deck, cls.more_money)

        actions.sort(key=score, reverse=True)
        try:
            player.action(actions[0])
        except Exception:
            break

    provinces_left = player.game.stock.province_qty
    safety = 0
    while player.purchases_left > 0 and safety < 10:
        safety += 1
        money = player.money + player.hand.money
        stock = player.game.stock
        choice: CardName | None = None
        if money >= 8 and stock.quantity(CardName.PROVINCE) > 0:
            choice = CardName.PROVINCE
        elif money >= 6 and stock.quantity(CardName.GOLD) > 0:
            choice = CardName.GOLD
        elif money >= 5 and provinces_left <= 5 and stock.quantity(CardName.DUCHY) > 0:
            choice = CardName.DUCHY
        elif (
            money >= 5
            and stock.quantity(CardName.CURSE) > 0
            and stock.quantity(CardName.WITCH) > 0
        ):
            choice = CardName.WITCH
        elif money >= 4 and stock.quantity(CardName.SMITHY) > 0:
            owned = sum(
                1
                for c in (player.hand + player.deck + player.discard + player.played_cards)
                if c == CardName.SMITHY
            )
            if owned < 1:
                choice = CardName.SMITHY
        if choice is None and money >= 3 and stock.quantity(CardName.SILVER) > 0:
            choice = CardName.SILVER
        if (
            choice is None
            and money >= 2
            and provinces_left <= 2
            and stock.quantity(CardName.ESTATE) > 0
        ):
            choice = CardName.ESTATE
        if choice is None:
            break
        try:
            player.buy(choice)
        except Exception:
            break
    player.end_turn()


def play_random_turn(player: Player) -> None:
    player.start_turn()
    safety = 0
    while player.actions_left > 0 and player.hand.contains_action() and safety < 15:
        safety += 1
        actions = [c for c in player.hand if Card.class_(c).is_action]
        if not actions:
            break
        try:
            player.action(random.choice(actions))
        except Exception:
            break
    safety = 0
    while player.purchases_left > 0 and safety < 8:
        safety += 1
        money = player.money + player.hand.money
        buyables = [
            name
            for name, cls in Card.types.items()
            if cls.cost <= money
            and name in player.game.stock
            and player.game.stock.quantity(name) > 0
            and name != CardName.COLONY
        ]
        if not buyables:
            break
        try:
            player.buy(random.choice(buyables))
        except Exception:
            break
    player.end_turn()


TurnFn = Callable[[Player], None]


def run_game(
    *,
    n_players: int = 2,
    max_turns: int = 120,
    opponent: str = "bm",
) -> dict:
    game_id = uuid.uuid4().hex
    strat.init_game(game_id)

    game = Game()
    us = Player("Groupe 5")
    us.hooks = StrategyHooks(game_id)
    game.add_player(us)

    opponents: list[tuple[Player, TurnFn]] = []
    for i in range(n_players - 1):
        opp = Player(f"Adverse-{i+1}")
        opp.hooks = DefaultPlayerHooks()
        game.add_player(opp)
        fn = play_random_turn if opponent == "random" else play_big_money_turn
        opponents.append((opp, fn))

    game.start()

    turns = 0
    while not game.finished and turns < max_turns:
        turns += 1
        play_strategy_turn(us, game_id)
        if game.finished:
            break
        for opp, fn in opponents:
            if opp.eliminated:
                continue
            fn(opp)
            if game.finished:
                break

    strat.end_game_state(game_id)
    scores = {p.name: p.score()["score"] for p in game.players}
    our = scores["Groupe 5"]
    best_other = max(s for n, s in scores.items() if n != "Groupe 5")
    return {
        "scores": scores,
        "our": our,
        "win": our > best_other and our > -1000,
        "tie": our == best_other and our > -1000,
        "crash": our <= -1000,
        "turns": turns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Arbitre local : scores EXACTS (VP) des parties jouées",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=80,
        help="Nombre exact de parties à jouer (défaut 80 ≈ 1 h serveur)",
    )
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--opponent", choices=("bm", "random"), default="bm")
    parser.add_argument(
        "--show-each",
        action="store_true",
        help="Afficher le score VP de chaque partie",
    )
    args = parser.parse_args()

    wins = ties = losses = crashes = 0
    our_scores: list[int] = []
    opp_best_scores: list[int] = []
    results: list[dict] = []

    print(
        f"Arbitre local — {args.games} parties exactes "
        f"({args.players} joueurs, vs {args.opponent})"
    )
    t0 = time.perf_counter()
    for i in range(args.games):
        result = run_game(n_players=args.players, opponent=args.opponent)
        results.append(result)
        our_scores.append(result["our"])
        others = [s for n, s in result["scores"].items() if n != "Groupe 5"]
        opp_best_scores.append(max(others))

        if result["crash"]:
            crashes += 1
            losses += 1
            tag = "CRASH"
        elif result["win"]:
            wins += 1
            tag = "WIN"
        elif result["tie"]:
            ties += 1
            tag = "NUL"
        else:
            losses += 1
            tag = "PERDU"

        if args.show_each:
            print(
                f"  partie {i+1:3d}  {tag:5s}  "
                f"nous={result['our']:5d}  adverse={max(others):5d}"
            )
        elif (i + 1) % 20 == 0:
            print(f"  … {i+1}/{args.games}")

    elapsed = time.perf_counter() - t0
    total_vp = sum(our_scores)
    avg_vp = total_vp / len(our_scores)
    avg_opp = sum(opp_best_scores) / len(opp_best_scores)

    print()
    print("=" * 56)
    print(" SCORES EXACTS (parties réellement jouées)")
    print("=" * 56)
    print(f" Parties jouées     : {args.games}")
    print(f" Temps de calcul    : {elapsed:.1f}s")
    print(f" Victoires exactes  : {wins}")
    print(f" Nuls exacts        : {ties}")
    print(f" Défaites exactes   : {losses}")
    print(f" Crashes            : {crashes}")
    print(f" Taux de victoire   : {wins}/{args.games} = {100*wins/args.games:.1f}%")
    print()
    print(f" Score VP total     : {total_vp}")
    print(f" Score VP moyen     : {avg_vp:.2f}")
    print(f" Score VP min/max   : {min(our_scores)} / {max(our_scores)}")
    print(f" VP moyen adverse   : {avg_opp:.2f}")
    print()
    if crashes:
        print(" Verdict : crashes détectés — strat non fiable.")
    elif wins > losses:
        print(
            f" Verdict : on GAGNE ({wins} wins > {losses} défaites), "
            f"score moyen exact = {avg_vp:.2f} VP."
        )
    elif wins == losses:
        print(
            f" Verdict : ÉGALITÉ ({wins} wins / {losses} défaites), "
            f"score moyen exact = {avg_vp:.2f} VP."
        )
    else:
        print(
            f" Verdict : on PERD ({wins} wins < {losses} défaites), "
            f"score moyen exact = {avg_vp:.2f} VP."
        )
    print("=" * 56)
    print(
        "Ces chiffres sont exacts pour l'arbitre local "
        "(pas le classement Elo du serveur)."
    )


if __name__ == "__main__":
    main()
