"""Simule un tour Big Money contre le serveur local (port 8000)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
GAME_ID = "test-1"


def request(method: str, path: str, body: dict | None = None) -> dict | str:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "X-Game-Id": GAME_ID,
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


def main() -> None:
    print("1) /name ->", request("GET", "/name"))
    print("2) /start_turn ->", request("GET", "/start_turn"))

    # Nom volontairement différent de "Groupe 5" : on doit quand même acheter
    # grâce à la main non nulle (comme en match réel).
    body = {
        "finished": False,
        "players": [
            {
                "name": "AutreNomArbitre",
                "score": 0,
                "hand": {"quantities": {"copper": 3, "silver": 1, "estate": 1}},
            },
            {"name": "Adverse", "score": 0, "hand": None},
        ],
        "stock": {
            "quantities": {
                "province": 8,
                "gold": 30,
                "silver": 40,
                "duchy": 8,
                "estate": 8,
            }
        },
    }

    print("3) /play (1er) ->", request("POST", "/play", body))
    print("4) /play (2e)  ->", request("POST", "/play", body))
    print()
    print("Attendu: BUY silver puis END_TURN (meme avec un nom different)")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print("Serveur inaccessible. Lance d'abord dans un autre terminal:")
        print("  .\\.venv\\Scripts\\uvicorn.exe main:app --reload --port 8000")
        print("Erreur:", exc)
        sys.exit(1)
