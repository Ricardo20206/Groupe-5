"""Tests Big Money (format vincent_bm)."""

from __future__ import annotations

from dopynion.data_model import CardName, Cards, Game, Player

from strategy import choose_buy, decide_play, end_game_state, reset_turn, _memory


def make_game(
    hand: dict[CardName, int],
    *,
    provinces: int = 8,
    smithy_stock: int = 10,
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
                CardName.SMITHY: smithy_stock,
            }
        ),
    )


def check(label: str, got: object, expected: object) -> None:
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r} (attendu {expected!r})")
    assert got == expected, f"{label}: {got!r} != {expected!r}"


def main() -> None:
    g = make_game({CardName.COPPER: 2})
    mem = _memory("prio")
    mem.smithies_bought = 0
    check("$3 silver", choose_buy(g, 3, mem), CardName.SILVER)
    check("$4 smithy", choose_buy(g, 4, mem), CardName.SMITHY)
    check("$5 p8 silver", choose_buy(g, 5, mem), CardName.SMITHY)
    mem.smithies_bought = 1
    check("$5 p8 apres smithy -> silver", choose_buy(g, 5, mem), CardName.SILVER)
    check("$5 p5 duchy", choose_buy(make_game({}, provinces=5), 5, mem), CardName.DUCHY)
    check("$5 p6 silver", choose_buy(make_game({}, provinces=6), 5, mem), CardName.SILVER)
    check("$2 p2 estate", choose_buy(make_game({}, provinces=2), 2, mem), CardName.ESTATE)
    check("$2 p8 rien", choose_buy(make_game({}, provinces=8), 2, mem), None)
    check(
        "$4 sans pile smithy",
        choose_buy(make_game({}, smithy_stock=0), 4, mem),
        CardName.SILVER,
    )

    end_game_state("t1")
    reset_turn("t1")
    gs = make_game({CardName.SMITHY: 1, CardName.COPPER: 2, CardName.SILVER: 1})
    check("ACTION smithy", decide_play(gs, "t1"), "ACTION smithy")
    check("puis BUY silver", decide_play(gs, "t1"), "BUY silver")
    check("puis END_TURN", decide_play(gs, "t1"), "END_TURN")

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
