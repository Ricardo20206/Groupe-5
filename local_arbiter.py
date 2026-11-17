"""
Arbitre local dopynion pour tester la stratégie rapidement.

Exemple :
  python local_arbiter.py
  python local_arbiter.py --games 300 --players 3
  python local_arbiter.py --hours 1 --games-per-hour 80
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

# Évite d'écrire des centaines de fichiers dans games/ pendant le bench.
_BENCH_DIR = Path(__file__).resolve().parent / "games_bench"
_BENCH_DIR.mkdir(exist_ok=True)
dopynion_record.records_dir = _BENCH_DIR


def _silence_records() -> None:
    """Record minimal : pas d'I/O disque à chaque action."""

    class QuietRecord:  # noqa: D101
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
    """Branche les hooks de strategy.py sur l'arbitre local."""

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
    """Un tour complet piloté par strategy.choose_action / choose_buy."""
    mem = strat._memory(game_id)
    player.start_turn()

    safety = 0
    while player.actions_left > 0 and player.hand.contains_action() and safety < 30:
        safety += 1
        game_data = player.game.state
        card = strat.choose_action(player.hand.state, game_data)
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
        game_data = player.game.state
        card = strat.choose_buy(game_data, money, mem, player.hand.state)
        if card is None:
            break
        try:
            player.buy(card)
            strat._register_buy(mem, card)
        except Exception:
            break

    player.end_turn()


def play_big_money_turn(player: Player) -> None:
    """Adversaire BM simple : 1 Smithy/Witch, Or, Province, Duché tardif."""
    player.start_turn()

    # Actions : villages puis attaque/draw
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
            # 1 smithy max : approx via deck
            owned = sum(
                1
                for c in (player.hand + player.deck + player.discard + player.played_cards)
                if c == CardName.SMITHY
            )
            if owned < 1:
                choice = CardName.SMITHY
        if choice is None and money >= 3 and stock.quantity(CardName.SILVER) > 0:
            choice = CardName.SILVER
        if choice is None and money >= 2 and provinces_left <= 2 and stock.quantity(CardName.ESTATE) > 0:
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
            if cls.cost <= money and name in player.game.stock and player.game.stock.quantity(name) > 0
        ]
        # Évite Colonie / piles exotiques trop chères inutiles
        buyables = [b for b in buyables if b != CardName.COLONY]
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
        if opponent == "random":
            opponents.append((opp, play_random_turn))
        else:
            opponents.append((opp, play_big_money_turn))

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


def fetch_live_ranking() -> dict[str, tuple[int, int, str]]:
    """{clé: (elo, parties, url)} pour einstein / empire / #1."""
    import re
    import urllib.request

    html = urllib.request.urlopen(
        "https://dopynion.lecalamar.fr/",
        timeout=20,
    ).read().decode("utf-8")
    rows = sorted(
        (
            (int(elo), int(games), url)
            for url, elo, games in re.findall(
                r"<tr><td>(.*?)</td><td>(\d+)</td><td>(\d+)</td></tr>",
                html,
            )
        ),
        reverse=True,
    )
    out: dict[str, tuple[int, int, str]] = {}
    if rows:
        out["leader"] = (rows[0][0], rows[0][1], rows[0][2])
    for elo, games, url in rows:
        if "einstein" in url:
            out["einstein"] = (elo, games, url)
        if "le-4eme-empire.alwaysdata" in url:
            out["empire"] = (elo, games, url)
    # Plateau = moyenne Elo top 8 (adversaires typiques)
    top8 = [e for e, _, _ in rows[:8]]
    if top8:
        out["field"] = (int(sum(top8) / len(top8)), 0, "top8")
    return out


def simulate_hour_elo(
    winrate: float,
    *,
    games: int,
    our_elo: float,
    field_elo: float,
    k: float = 16.0,
    samples: int = 200,
) -> dict:
    """Simule `samples` trajectoires d'1 h (victoires aléatoires selon winrate)."""
    finals: list[float] = []
    for _ in range(samples):
        elo = float(our_elo)
        for _ in range(games):
            expected = 1.0 / (1.0 + 10 ** ((field_elo - elo) / 400.0))
            score = 1.0 if random.random() < winrate else 0.0
            elo += k * (score - expected)
        finals.append(elo)
    finals.sort()
    mean = sum(finals) / len(finals)
    return {
        "games": games,
        "elo_start": our_elo,
        "elo_mean": round(mean, 1),
        "elo_p10": round(finals[int(0.10 * len(finals))], 1),
        "elo_p50": round(finals[int(0.50 * len(finals))], 1),
        "elo_p90": round(finals[int(0.90 * len(finals))], 1),
        "delta_mean": round(mean - our_elo, 1),
        "field": field_elo,
    }


def print_rapport(
    *,
    total: int,
    wins: int,
    ties: int,
    losses: int,
    crashes: int,
    vp: list[int],
    elapsed: float,
    players: int,
    opponent: str,
    hours: float,
    games_per_hour: int,
    our_elo: float,
    field_elo: float,
    leader_elo: float,
    live: bool,
) -> None:
    wr = wins / total if total else 0.0
    games_hour = int(games_per_hour * hours)
    sim = simulate_hour_elo(
        wr,
        games=games_hour,
        our_elo=our_elo,
        field_elo=field_elo,
    )

    print("\n" + "=" * 60)
    print(" VERDICT ARBITRE LOCAL")
    print("=" * 60)
    print(f" Parties testées     : {total} ({players} joueurs, vs {opponent})")
    print(f" Temps de calcul     : {elapsed:.1f}s")
    print(f" Victoires           : {wins}/{total}  ({wr:.0%})")
    print(f" Nuls / Défaites     : {ties} / {losses}")
    print(f" Crashes (-10000)    : {crashes}")
    print(f" Score VP moyen      : {sum(vp)/len(vp):.1f}  (min {min(vp)}, max {max(vp)})")

    gagne_local = wr >= 0.55 and crashes == 0
    print()
    if crashes:
        print(" → En local : NON FIABLE (il y a des crashes).")
    elif wr >= 0.60:
        print(" → En local : OUI, on gagne clairement contre cet adversaire.")
    elif wr >= 0.55:
        print(" → En local : OUI, on gagne plus souvent qu'on ne perd.")
    elif wr >= 0.45:
        print(" → En local : ÉGALITÉ / MATCHS SERRÉS (pas assez pour viser le #1).")
    else:
        print(" → En local : NON, on perd trop souvent.")

    print()
    print("-" * 60)
    print(f" ESTIMATION APRÈS {hours:g} HEURE(S) SUR LE SERVEUR")
    print("-" * 60)
    src = "classement live" if live else "valeurs manuelles"
    print(f" Elo actuel (einstein): {our_elo:.0f}  ({src})")
    print(f" Elo #1 actuel        : {leader_elo:.0f}")
    print(f" Plateau adversaires  : {field_elo:.0f} (moyenne top)")
    print(f" Parties simulées / h : {games_hour}")
    print(f" Winrate utilisé         : {wr:.0%}")
    print()
    print(f" Elo estimé (moyenne) : {sim['elo_mean']:.0f}  ({sim['delta_mean']:+.0f})")
    print(f" Elo estimé (médiane) : {sim['elo_p50']:.0f}")
    print(f" Fourchette probable  : {sim['elo_p10']:.0f} … {sim['elo_p90']:.0f}")
    print()

    atteint_top = sim["elo_p50"] >= leader_elo
    approche = sim["elo_p90"] >= leader_elo - 50
    if atteint_top:
        print(
            f" → Après {hours:g} h : OUI, score estimé ~{sim['elo_p50']:.0f} "
            f"— suffisant pour viser la 1ère place (#{leader_elo:.0f} aujourd'hui)."
        )
    elif approche:
        print(
            f" → Après {hours:g} h : PRESQUE — score estimé ~{sim['elo_p50']:.0f}, "
            f"encore sous le #1 ({leader_elo:.0f}), mais dans la course."
        )
    elif sim["delta_mean"] > 30:
        print(
            f" → Après {hours:g} h : ON MONTE (≈ {sim['elo_p50']:.0f}), "
            f"mais PAS encore 1er (il faut ~{leader_elo:.0f})."
        )
    else:
        print(
            f" → Après {hours:g} h : PAS EN TÊTE — score estimé ≈ {sim['elo_p50']:.0f} "
            f"(#1 à {leader_elo:.0f}). Il faut une strat plus forte."
        )
    print("=" * 60)
    print(
        "Note : l'adversaire local (Big Money) est plus faible que Empire/bowser ; "
        "sur le serveur le gain réel peut être un peu plus bas."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Arbitre local + verdict 1 h")
    parser.add_argument("--games", type=int, default=200, help="Parties de test local")
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--opponent", choices=("bm", "random"), default="bm")
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--games-per-hour", type=int, default=80)
    parser.add_argument("--our-elo", type=float, default=None)
    parser.add_argument("--field-elo", type=float, default=None)
    parser.add_argument("--leader-elo", type=float, default=None)
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Ne pas lire le classement dopynion",
    )
    args = parser.parse_args()

    live = not args.no_live
    our_elo = args.our_elo
    field_elo = args.field_elo
    leader_elo = args.leader_elo
    if live:
        try:
            ranking = fetch_live_ranking()
            if our_elo is None and "einstein" in ranking:
                our_elo = float(ranking["einstein"][0])
            if leader_elo is None and "leader" in ranking:
                leader_elo = float(ranking["leader"][0])
            if field_elo is None and "field" in ranking:
                field_elo = float(ranking["field"][0])
            print("Classement live chargé.")
            if "einstein" in ranking:
                print(f"  einstein = {ranking['einstein'][0]}")
            if "leader" in ranking:
                print(f"  #1       = {ranking['leader'][0]}  ({ranking['leader'][2]})")
            if "empire" in ranking:
                print(f"  Empire   = {ranking['empire'][0]}")
        except Exception as exc:
            print(f"Classement live indisponible ({exc}), valeurs par défaut.")
            live = False

    our_elo = 1180.0 if our_elo is None else our_elo
    field_elo = 1400.0 if field_elo is None else field_elo
    leader_elo = 1495.0 if leader_elo is None else leader_elo

    wins = ties = losses = crashes = 0
    vp: list[int] = []
    t0 = time.perf_counter()
    for i in range(args.games):
        result = run_game(n_players=args.players, opponent=args.opponent)
        vp.append(result["our"])
        if result["crash"]:
            crashes += 1
            losses += 1
        elif result["win"]:
            wins += 1
        elif result["tie"]:
            ties += 1
        else:
            losses += 1
        if (i + 1) % 50 == 0:
            print(f"  test {i+1}/{args.games}…")

    elapsed = time.perf_counter() - t0
    print_rapport(
        total=args.games,
        wins=wins,
        ties=ties,
        losses=losses,
        crashes=crashes,
        vp=vp,
        elapsed=elapsed,
        players=args.players,
        opponent=args.opponent,
        hours=args.hours,
        games_per_hour=args.games_per_hour,
        our_elo=our_elo,
        field_elo=field_elo,
        leader_elo=leader_elo,
        live=live,
    )


if __name__ == "__main__":
    main()
