"""Tests unitaires Big Money sûr (sans Action)."""

from __future__ import annotations

from dopynion.data_model import CardName, Cards, Game, Player

from strategy import choose_buy, decide_play, end_game_state, hand_money, reset_turn


def make_game(
    hand: dict[CardName, int],
    *,
    provinces: int = 8,
) -> Game:
    return Game(
        finished=False,
        players=[
            Player(name="BotMatch", hand=Cards(quantities=hand), score=0),
            Player(name="Adverse", hand=None, score=0),
        ],
        stock=Cards(
            quantities={
                CardName.PROVINCE: provinces,
                CardName.GOLD: 30,
                CardName.SILVER: 40,
                CardName.DUCHY: 8,
                CardName.ESTATE: 8,
                CardName.SMITHY: 10,
            }
        ),
    )


def check(label: str, got: object, expected: object) -> None:
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r} (attendu {expected!r})")
    assert got == expected, f"{label}: {got!r} != {expected!r}"


def main() -> None:
    check(
        "argent",
        hand_money(Cards(quantities={CardName.COPPER: 3, CardName.SILVER: 1})),
        5,
    )

    g = make_game({CardName.COPPER: 2}, provinces=8)
    check("$2 debut -> rien", choose_buy(g, 2), None)
    check("$3 -> silver", choose_buy(g, 3), CardName.SILVER)
    check("$4 -> silver (pas smithy)", choose_buy(g, 4), CardName.SILVER)
    check("$5 debut -> silver", choose_buy(g, 5), CardName.SILVER)
    check("$6 -> gold", choose_buy(g, 6), CardName.GOLD)
    check("$8 -> province", choose_buy(g, 8), CardName.PROVINCE)

    g_end = make_game({CardName.COPPER: 5}, provinces=4)
    check("$5 fin -> duchy", choose_buy(g_end, 5), CardName.DUCHY)

    end_game_state("t1")
    reset_turn("t1")
    g5 = make_game({CardName.COPPER: 3, CardName.SILVER: 1})
    check("BUY silver", decide_play(g5, "t1"), "BUY silver")
    check("END_TURN", decide_play(g5, "t1"), "END_TURN")

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
