"""Scénarios HTTP contre le serveur local."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def request(
    method: str,
    path: str,
    game_id: str,
    body: dict | None = None,
) -> dict | str:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "X-Game-Id": game_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read().decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def body_for(
    hand: dict,
    provinces: int = 8,
    *,
    stock_extra: dict | None = None,
) -> dict:
    stock = {
        "province": provinces,
        "gold": 30,
        "silver": 40,
        "duchy": 8,
        "estate": 8,
        "copper": 60,
        "curse": 30,
    }
    if stock_extra:
        stock.update(stock_extra)
    return {
        "finished": False,
        "players": [
            {"name": "AutreNom", "score": 0, "hand": {"quantities": hand}},
            {"name": "Adverse", "score": 0, "hand": None},
        ],
        "stock": {"quantities": stock},
    }


def run_scenario(
    title: str,
    game_id: str,
    hand: dict,
    expected: list[str],
    *,
    provinces: int = 8,
    stock_extra: dict | None = None,
) -> None:
    print(f"\n=== {title} ===")
    request("GET", "/start_game", game_id)
    request("GET", "/start_turn", game_id)
    payload = body_for(hand, provinces=provinces, stock_extra=stock_extra)
    for i, exp in enumerate(expected, start=1):
        got = request("POST", "/play", game_id, payload)
        decision = got["decision"] if isinstance(got, dict) else got
        ok = "OK" if decision == exp else "FAIL"
        print(f"  play #{i} -> {decision!r} [{ok}] (attendu {exp!r})")
        if decision != exp:
            raise SystemExit(1)


def main() -> None:
    print("/name ->", request("GET", "/name", "boot"))
    run_scenario(
        "BM $6 gold (pas d'actions kingdom)",
        "s1",
        {"gold": 2},
        ["BUY gold", "END_TURN"],
    )
    run_scenario(
        "$5 market si dispo",
        "s2",
        {"copper": 3, "silver": 1},
        ["BUY market", "END_TURN"],
        stock_extra={"market": 10},
    )
    run_scenario(
        "$5 witch si curse",
        "s3",
        {"copper": 3, "silver": 1},
        ["BUY witch", "END_TURN"],
        stock_extra={"witch": 10, "market": 10},
    )
    run_scenario(
        "$8 province",
        "s4",
        {"gold": 2, "silver": 1},
        ["BUY province", "END_TURN"],
    )
    run_scenario(
        "Port puis Smithy",
        "s5",
        {"port": 1, "smithy": 1, "copper": 2, "silver": 1},
        ["ACTION port", "ACTION smithy", "BUY port", "END_TURN"],
        stock_extra={"port": 10, "smithy": 10},
    )
    print("\nTous les scenarios HTTP OK.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print("Lance: .\\.venv\\Scripts\\uvicorn.exe main:app --reload --port 8000")
        print(exc)
        sys.exit(1)
