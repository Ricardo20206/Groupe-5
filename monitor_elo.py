"""Snapshot Elo einstein / Empire / officinal depuis dopynion."""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://dopynion.lecalamar.fr/"
OUT = Path(__file__).with_name("elo_history.jsonl")
WATCH = ("einstein", "empire", "ricardo", "bowser", "marioluigi")


def fetch() -> list[tuple[int, int, str]]:
    html = urllib.request.urlopen(URL, timeout=25).read().decode("utf-8")
    rows = [
        (int(elo), int(games), url)
        for url, elo, games in re.findall(
            r"<tr><td>(.*?)</td><td>(\d+)</td><td>(\d+)</td></tr>", html
        )
    ]
    return sorted(rows, reverse=True)


def main() -> None:
    rows = fetch()
    now = datetime.now(timezone.utc).isoformat()
    focus = {
        url: {"elo": elo, "games": games, "rank": i}
        for i, (elo, games, url) in enumerate(rows, 1)
        if any(w in url for w in WATCH)
    }
    payload = {"ts": now, "focus": focus}
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[{now}]")
    for i, (elo, games, url) in enumerate(rows, 1):
        mark = " <<" if any(w in url for w in ("einstein", "empire", "ricardo")) else ""
        if i <= 12 or mark:
            print(f"{i:>2}. {elo:>5}  {url}{mark}")
    ein = next((e for e, _, u in rows if "einstein" in u), None)
    emp = next((e for e, _, u in rows if "le-4eme-empire.alwaysdata" in u), None)
    if ein is not None and emp is not None:
        print(f"ecart Empire-einstein: {emp - ein}")


if __name__ == "__main__":
    main()
