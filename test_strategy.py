"""Tests stratégie adaptative au kingdom."""

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
    stock: dict[CardName, int] | None = None,
) -> Game:
    base: dict[CardName, int] = {
        CardName.PROVINCE: provinces,
        CardName.GOLD: 30,
        CardName.SILVER: 40,
        CardName.DUCHY: 8,
        CardName.ESTATE: 8,
        CardName.CURSE: 30,
        CardName.COPPER: 60,
    }
    if stock:
        base.update(stock)
    return Game(
        finished=False,
        players=[
            Player(name="BotMatch", hand=Cards(quantities=hand), score=0),
            Player(name="Adverse", hand=None, score=0),
        ],
        stock=Cards(quantities=base),
    )


def check(label: str, got: object, expected: object) -> None:
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r} (attendu {expected!r})")
    assert got == expected, f"{label}: {got!r} != {expected!r}"


def main() -> None:
    init_game("prio")
    mem = _memory("prio")

    # Kingdom sans actions moteur -> Big Money
    g_bm = make_game({})
    check("$3 BM silver", choose_buy(g_bm, 3, mem), CardName.SILVER)
    check("$6 BM gold", choose_buy(g_bm, 6, mem), CardName.GOLD)
    check("$8 BM province", choose_buy(g_bm, 8, mem), CardName.PROVINCE)

    # Kingdom avec Hireling
    g_h = make_game({}, stock={CardName.HIRELING: 10})
    check("$6 hireling", choose_buy(g_h, 6, mem), CardName.HIRELING)

    # Kingdom style partie réelle : market/port/magpie…
    g_m = make_game(
        {},
        stock={
            CardName.MARKET: 10,
            CardName.PORT: 10,
            CardName.MAGPIE: 10,
            CardName.BANDIT: 10,
            CardName.DISTANTSHORE: 10,
        },
    )
    check("$5 market", choose_buy(g_m, 5, mem), CardName.MARKET)
    check("$4 port", choose_buy(g_m, 4, mem), CardName.PORT)

    # Witch si malédictions
    g_w = make_game({}, stock={CardName.WITCH: 10, CardName.MARKET: 10})
    check("$5 witch avant market", choose_buy(g_w, 5, mem), CardName.WITCH)
    g_nocurse = make_game(
        {},
        stock={CardName.WITCH: 10, CardName.MARKET: 10, CardName.CURSE: 0},
    )
    check("$5 sans curse -> market", choose_buy(g_nocurse, 5, mem), CardName.MARKET)

    # Fin de partie
    check(
        "$5 p4 duchy",
        choose_buy(make_game({}, provinces=4, stock={CardName.MARKET: 10}), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 p4 stop actions -> silver",
        choose_buy(make_game({}, provinces=4, stock={CardName.PORT: 10}), 4, mem),
        CardName.SILVER,
    )

    # Actions : +actions d'abord
    hand = Cards(
        quantities={CardName.MARKET: 1, CardName.SMITHY: 1, CardName.COPPER: 1}
    )
    check(
        "market avant smithy",
        choose_action(hand, make_game({}, stock={CardName.MARKET: 1, CardName.SMITHY: 1})),
        CardName.MARKET,
    )

    end_game_state("t1")
    init_game("t1")
    reset_turn("t1")
    gs = make_game(
        {
            CardName.PORT: 1,
            CardName.SMITHY: 1,
            CardName.SILVER: 1,
            CardName.COPPER: 2,
        },
        stock={CardName.PORT: 10, CardName.SMITHY: 10, CardName.MARKET: 10},
    )
    check("ACTION port", decide_play(gs, "t1"), "ACTION port")
    check("ACTION smithy", decide_play(gs, "t1"), "ACTION smithy")
    # silver($2)+2 copper = $4 -> port (encore sous cap)
    check("BUY port", decide_play(gs, "t1"), "BUY port")
    check("END_TURN", decide_play(gs, "t1"), "END_TURN")

    init_game("A")
    init_game("B")
    _memory("A").bought[CardName.MARKET] = 9
    check("isolation", _memory("B").bought.get(CardName.MARKET, 0), 0)

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
