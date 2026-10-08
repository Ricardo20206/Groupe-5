"""Compare notre bot local au comportement vincent_bm."""

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


def body_for(hand: dict, provinces: int = 8, smithy: int = 10) -> dict:
    return {
        "finished": False,
        "players": [
            {"name": "AutreNom", "score": 0, "hand": {"quantities": hand}},
            {"name": "Adverse", "score": 0, "hand": None},
        ],
        "stock": {
            "quantities": {
                "province": provinces,
                "gold": 30,
                "silver": 40,
                "duchy": 8,
                "estate": 8,
                "smithy": smithy,
            }
        },
    }


def run_scenario(
    title: str,
    game_id: str,
    hand: dict,
    expected: list[str],
    *,
    provinces: int = 8,
    smithy: int = 10,
) -> None:
    print(f"\n=== {title} ===")
    request("GET", "/start_turn", game_id)
    payload = body_for(hand, provinces=provinces, smithy=smithy)
    for i, exp in enumerate(expected, start=1):
        got = request("POST", "/play", game_id, payload)
        decision = got["decision"] if isinstance(got, dict) else got
        ok = "OK" if decision == exp else "FAIL"
        print(f"  play #{i} -> {decision!r} [{ok}] (attendu {exp!r})")
        if decision != exp:
            raise SystemExit(1)


def main() -> None:
    print("/name ->", request("GET", "/name", "boot"))
    run_scenario("$5 -> smithy", "s1", {"copper": 3, "silver": 1}, ["BUY smithy", "END_TURN"])
    run_scenario(
        "$5 fin -> duchy",
        "s2",
        {"copper": 3, "silver": 1},
        ["BUY duchy", "END_TURN"],
        provinces=4,
    )
    run_scenario("$8 -> province", "s3", {"gold": 2, "silver": 1}, ["BUY province", "END_TURN"])
    run_scenario(
        "ACTION smithy puis silver",
        "s4",
        {"smithy": 1, "copper": 2, "silver": 1},
        ["ACTION smithy", "BUY silver", "END_TURN"],
    )
    run_scenario(
        "$4 sans smithy en stock -> silver",
        "s5",
        {"copper": 2, "silver": 1},
        ["BUY silver", "END_TURN"],
        smithy=0,
    )
    print("\nTous les scenarios HTTP OK.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print("Lance: .\\.venv\\Scripts\\uvicorn.exe main:app --reload --port 8000")
        print(exc)
        sys.exit(1)
