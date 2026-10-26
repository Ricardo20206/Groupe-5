"""Tests moteur Village/Smithy + cartes avancées."""

from __future__ import annotations

from dopynion.data_model import CardName, Cards, Game, Player

from strategy import (
    choose_action,
    choose_buy,
    decide_play,
    end_game_state,
    init_game,
    reset_turn,
    _memory,
)


def make_game(
    hand: dict[CardName, int],
    *,
    provinces: int = 8,
    stock_extra: dict[CardName, int] | None = None,
) -> Game:
    stock: dict[CardName, int] = {
        CardName.PROVINCE: provinces,
        CardName.GOLD: 30,
        CardName.SILVER: 40,
        CardName.DUCHY: 8,
        CardName.ESTATE: 8,
        CardName.SMITHY: 10,
        CardName.VILLAGE: 10,
        CardName.FARMINGVILLAGE: 10,
        CardName.WITCH: 10,
        CardName.COUNCILROOM: 10,
        CardName.HIRELING: 10,
        CardName.DISTANTSHORE: 10,
        CardName.CURSE: 30,
    }
    if stock_extra:
        stock.update(stock_extra)
    return Game(
        finished=False,
        players=[
            Player(name="BotMatch", hand=Cards(quantities=hand), score=0),
            Player(name="Adverse", hand=None, score=0),
        ],
        stock=Cards(quantities=stock),
    )


def check(label: str, got: object, expected: object) -> None:
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r} (attendu {expected!r})")
    assert got == expected, f"{label}: {got!r} != {expected!r}"


def main() -> None:
    init_game("prio")
    mem = _memory("prio")
    g = make_game({CardName.COPPER: 2})

    check("$3 village", choose_buy(g, 3, mem), CardName.VILLAGE)
    check("$4 farmingvillage", choose_buy(g, 4, mem), CardName.FARMINGVILLAGE)
    check("$5 witch", choose_buy(g, 5, mem), CardName.WITCH)
    check("$6 hireling", choose_buy(g, 6, mem), CardName.HIRELING)
    check("$8 province", choose_buy(g, 8, mem), CardName.PROVINCE)

    mem.hirelings_bought = 2
    check("$6 apres hirelings -> gold", choose_buy(g, 6, mem), CardName.GOLD)

    check(
        "$5 fin -> duchy",
        choose_buy(make_game({}, provinces=5), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 fin (stop actions) -> silver",
        choose_buy(make_game({}, provinces=4), 4, mem),
        CardName.SILVER,
    )
    check(
        "$5 sans maledictions -> councilroom",
        choose_buy(make_game({}, stock_extra={CardName.CURSE: 0}), 5, mem),
        CardName.COUNCILROOM,
    )
    check("$2 p2 estate", choose_buy(make_game({}, provinces=2), 2, mem), CardName.ESTATE)

    hand = Cards(
        quantities={
            CardName.VILLAGE: 1,
            CardName.SMITHY: 1,
            CardName.COPPER: 1,
        }
    )
    check("action village d'abord", choose_action(hand, g), CardName.VILLAGE)

    end_game_state("t1")
    init_game("t1")
    reset_turn("t1")
    gs = make_game(
        {
            CardName.VILLAGE: 1,
            CardName.SMITHY: 1,
            CardName.SILVER: 1,
            CardName.COPPER: 2,  # silver($2)+2×copper($1) = $4
        }
    )
    check("ACTION village", decide_play(gs, "t1"), "ACTION village")
    check("ACTION smithy", decide_play(gs, "t1"), "ACTION smithy")
    # $4 → Farming Village
    check("BUY farmingvillage", decide_play(gs, "t1"), "BUY farmingvillage")
    check("END_TURN", decide_play(gs, "t1"), "END_TURN")

    init_game("A")
    init_game("B")
    _memory("A").smithies_bought = 9
    check("memoire B isolee", _memory("B").smithies_bought, 0)

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
