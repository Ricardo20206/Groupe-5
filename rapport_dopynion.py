"""
Rapport aligné sur dopynion.lecalamar.fr

1) Parties locales avec le MÊME moteur dopynion que le site
   → scores VP exacts (mêmes règles / même calcul de points)

2) Classement Elo LU sur le site officiel
   → c'est le seul score de classement réel (einstein, #1, Empire)

L'Elo du site ne peut PAS être inventé en local : il ne change
que lorsque einstein joue vraiment sur le serveur.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from local_arbiter import run_game

HISTORY = Path(__file__).with_name("elo_history.jsonl")
URL = "https://dopynion.lecalamar.fr/"


def fetch_ranking() -> list[tuple[int, int, int, str]]:
    """[(rang, elo, parties, url), ...] trié par Elo desc."""
    html = urllib.request.urlopen(URL, timeout=25).read().decode("utf-8")
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
    return [(i, elo, games, url) for i, (elo, games, url) in enumerate(rows, 1)]


def find_bot(
    ranking: list[tuple[int, int, int, str]],
    needle: str,
) -> tuple[int, int, int, str] | None:
    for rank, elo, games, url in ranking:
        if needle in url:
            return rank, elo, games, url
    return None


def append_history(payload: dict) -> None:
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def last_einstein_elo() -> int | None:
    if not HISTORY.exists():
        return None
    lines = HISTORY.read_text(encoding="utf-8").strip().splitlines()
    for line in reversed(lines):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        elo = data.get("einstein_elo")
        if elo is not None:
            return int(elo)
    return None


def run_local_batch(games: int, players: int, opponent: str) -> dict:
    wins = ties = losses = crashes = 0
    our_vp: list[int] = []
    for i in range(games):
        result = run_game(n_players=players, opponent=opponent)
        our_vp.append(result["our"])
        if result["crash"]:
            crashes += 1
            losses += 1
        elif result["win"]:
            wins += 1
        elif result["tie"]:
            ties += 1
        else:
            losses += 1
        if (i + 1) % 20 == 0:
            print(f"  parties locales {i+1}/{games}…")
    return {
        "games": games,
        "players": players,
        "opponent": opponent,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "crashes": crashes,
        "vp_total": sum(our_vp),
        "vp_avg": round(sum(our_vp) / len(our_vp), 2),
        "vp_min": min(our_vp),
        "vp_max": max(our_vp),
        "winrate": round(100 * wins / games, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VP locaux (moteur dopynion) + Elo réel du site",
    )
    parser.add_argument("--games", type=int, default=80)
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--opponent", choices=("bm", "random"), default="bm")
    parser.add_argument(
        "--elo-only",
        action="store_true",
        help="Ne lire que le classement live (pas de parties locales)",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    print("=" * 60)
    print(" RAPPORT DOPYNION (site officiel + moteur local identique)")
    print("=" * 60)

    # --- Elo RÉEL depuis le site -----------------------------------------
    print("\n[1] Classement RÉEL lu sur dopynion.lecalamar.fr")
    ranking = fetch_ranking()
    einstein = find_bot(ranking, "einstein")
    empire = find_bot(ranking, "le-4eme-empire.alwaysdata")
    leader = ranking[0] if ranking else None

    if not einstein or not leader:
        raise SystemExit("Impossible de lire le classement live.")

    e_rank, e_elo, e_games, e_url = einstein
    l_rank, l_elo, l_games, l_url = leader
    prev = last_einstein_elo()
    delta = None if prev is None else e_elo - prev

    print(f"  #1      : Elo {l_elo}  (rang {l_rank})  {l_url}")
    if empire:
        print(f"  Empire  : Elo {empire[1]}  (rang {empire[0]})")
    print(f"  einstein: Elo {e_elo}  (rang {e_rank})  parties={e_games}")
    if delta is not None:
        print(f"  Variation depuis dernier rapport : {delta:+d} Elo")
    else:
        print("  Variation : (premier enregistrement)")

    append_history(
        {
            "ts": now,
            "einstein_elo": e_elo,
            "einstein_rank": e_rank,
            "einstein_games": e_games,
            "leader_elo": l_elo,
            "empire_elo": empire[1] if empire else None,
        }
    )

    if args.elo_only:
        print("\n(Mode --elo-only : pas de parties locales.)")
        print("=" * 60)
        return

    # --- Scores VP locaux (même moteur que le site) ----------------------
    print(
        f"\n[2] Parties locales — même moteur dopynion que le site "
        f"({args.games} parties, {args.players}j, vs {args.opponent})"
    )
    print(
        "    Les VP sont calculés comme sur dopynion "
        "(Province=6, Duché=3, etc.)."
    )
    t0 = time.perf_counter()
    local = run_local_batch(args.games, args.players, args.opponent)
    elapsed = time.perf_counter() - t0

    print(f"\n  Victoires     : {local['wins']}/{local['games']} ({local['winrate']}%)")
    print(f"  Nuls/Défaites : {local['ties']} / {local['losses']}")
    print(f"  Crashes       : {local['crashes']}")
    print(f"  VP total      : {local['vp_total']}")
    print(f"  VP moyen      : {local['vp_avg']}")
    print(f"  VP min/max    : {local['vp_min']} / {local['vp_max']}")
    print(f"  Durée calcul  : {elapsed:.1f}s")

    print("\n[3] Comment mesurer la montée einstein")
    print("  - Le score de CLASSEMENT réel = Elo ci-dessus (lu sur le site).")
    print("  - Relance ce script après le pull/restart, puis une heure plus tard :")
    print("      python rapport_dopynion.py --elo-only")
    print("  - La ligne « Variation » montrera la vraie montée/descente Elo.")
    print(
        "  - Impossible d'obtenir le même Elo en local : "
        "seules les parties serveur le modifient."
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
