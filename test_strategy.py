"""Tests unitaires Big Money+ (sans serveur)."""

from __future__ import annotations

from dopynion.data_model import CardName, Cards, Game, Player

from strategy import (
    choose_buy,
    decide_play,
    end_game_state,
    hand_money,
    reset_turn,
    _memory,
)


def make_game(
    hand: dict[CardName, int],
    *,
    provinces: int = 8,
    smithy_stock: int = 10,
    name: str = "BotMatch",
) -> Game:
    return Game(
        finished=False,
        players=[
            Player(name=name, hand=Cards(quantities=hand), score=0),
            Player(name="Adverse", hand=None, score=0),
        ],
        stock=Cards(
            quantities={
                CardName.PROVINCE: provinces,
                CardName.GOLD: 30,
                CardName.SILVER: 40,
                CardName.DUCHY: 8,
                CardName.ESTATE: 8,
                CardName.SMITHY: smithy_stock,
            }
        ),
    )


def check(label: str, got: object, expected: object) -> None:
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r} (attendu {expected!r})")
    assert got == expected, f"{label}: {got!r} != {expected!r}"


def main() -> None:
    print("=== Argent ===")
    check(
        "3c+1s",
        hand_money(Cards(quantities={CardName.COPPER: 3, CardName.SILVER: 1})),
        5,
    )

    print("=== Achats (mieux que Big Money pur) ===")
    g = make_game({CardName.COPPER: 2}, provinces=8)
    mem = _memory("prio")
    mem.smithies_bought = 0

    check("$2 debut -> rien (pas d'estate tot)", choose_buy(g, 2, mem), None)
    check("$3 -> silver", choose_buy(g, 3, mem), CardName.SILVER)
    check("$4 -> smithy", choose_buy(g, 4, mem), CardName.SMITHY)
    check("$5 debut (0 smithy) -> smithy", choose_buy(g, 5, mem), CardName.SMITHY)
    mem.smithies_bought = 1
    check("$5 debut (1 smithy) -> silver", choose_buy(g, 5, mem), CardName.SILVER)
    check("$6 -> gold", choose_buy(g, 6, mem), CardName.GOLD)
    check("$8 -> province", choose_buy(g, 8, mem), CardName.PROVINCE)

    g_end = make_game({CardName.COPPER: 5}, provinces=4)
    check("$5 fin -> duchy", choose_buy(g_end, 5, mem), CardName.DUCHY)
    g_late = make_game({CardName.COPPER: 2}, provinces=2)
    check("$2 tres fin -> estate", choose_buy(g_late, 2, mem), CardName.ESTATE)

    g_no_smithy = make_game({CardName.COPPER: 4}, smithy_stock=0)
    check("$4 sans pile smithy -> silver", choose_buy(g_no_smithy, 4, mem), CardName.SILVER)

    print("=== Tours ===")
    end_game_state("t1")
    reset_turn("t1")
    g5 = make_game({CardName.COPPER: 3, CardName.SILVER: 1}, provinces=8)
    check("$5 debut BUY smithy", decide_play(g5, "t1"), "BUY smithy")
    check("puis END_TURN", decide_play(g5, "t1"), "END_TURN")

    end_game_state("t2")
    reset_turn("t2")
    gs = make_game({CardName.SMITHY: 1, CardName.COPPER: 2, CardName.SILVER: 1})
    check("joue smithy", decide_play(gs, "t2"), "smithy")
    check("puis BUY silver", decide_play(gs, "t2"), "BUY silver")
    check("puis END_TURN", decide_play(gs, "t2"), "END_TURN")

    end_game_state("t3")
    reset_turn("t3")
    g4 = make_game({CardName.COPPER: 2, CardName.SILVER: 1})
    check("BUY smithy", decide_play(g4, "t3"), "BUY smithy")

    print()
    print("Tous les tests unitaires OK.")


if __name__ == "__main__":
    main()
