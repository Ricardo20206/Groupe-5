"""Tests stratégie type 4ème Empire."""

from __future__ import annotations

from dopynion.data_model import CardName, Cards, Game, Player

from strategy import (
    choose_action,
    choose_buy,
    choose_discard,
    choose_gain,
    choose_money_to_upgrade,
    choose_trash,
    confirm_discard,
    confirm_trash,
    decide_play,
    end_game_state,
    init_game,
    reset_turn,
    skip_reception,
    _memory,
)


def make_game(
    hand: dict[CardName, int],
    *,
    provinces: int = 8,
    stock: dict[CardName, int] | None = None,
    n_players: int = 2,
) -> Game:
    base: dict[CardName, int] = {
        CardName.PROVINCE: provinces,
        CardName.GOLD: 30,
        CardName.SILVER: 40,
        CardName.DUCHY: 8,
        CardName.ESTATE: 8,
        CardName.CURSE: 30,
        CardName.COPPER: 60,
        CardName.GARDENS: 12,
    }
    if stock:
        base.update(stock)
    players = [
        Player(name="BotMatch", hand=Cards(quantities=hand), score=0),
        Player(name="Adverse", hand=None, score=0),
    ]
    for i in range(max(0, n_players - 2)):
        players.append(Player(name=f"P{i}", hand=None, score=0))
    return Game(
        finished=False,
        players=players,
        stock=Cards(quantities=base),
    )


def empire_stock(**extra: int) -> dict[CardName, int]:
    base = {
        CardName.MILITIA: 10,
        CardName.WITCH: 10,
        CardName.FARMINGVILLAGE: 10,
        CardName.FESTIVAL: 10,
        CardName.GARDENS: 12,
        CardName.SMITHY: 10,
    }
    base.update(extra)
    return base


def check(label: str, got: object, expected: object) -> None:
    status = "OK" if got == expected else "FAIL"
    print(f"  [{status}] {label}: {got!r} (attendu {expected!r})")
    assert got == expected, f"{label}: {got!r} != {expected!r}"


def main() -> None:
    init_game("prio")
    mem = _memory("prio")

    check("$3 silver", choose_buy(make_game({}), 3, mem), CardName.SILVER)
    check("$6 gold", choose_buy(make_game({}), 6, mem), CardName.GOLD)
    check("$8 province", choose_buy(make_game({}), 8, mem), CardName.PROVINCE)
    check(
        "$6 or pas witch",
        choose_buy(make_game({}, stock=empire_stock()), 6, mem),
        CardName.GOLD,
    )
    check(
        "$5 witch prioritaire",
        choose_buy(make_game({}, stock=empire_stock()), 5, mem),
        CardName.WITCH,
    )
    mem.bought[CardName.WITCH] = 2
    check(
        "$5 apres 2 witch -> festival",
        choose_buy(make_game({}, stock=empire_stock()), 5, mem),
        CardName.FESTIVAL,
    )
    mem.bought[CardName.FESTIVAL] = 1
    check(
        "$4 militia",
        choose_buy(make_game({}, stock=empire_stock()), 4, mem),
        CardName.MILITIA,
    )
    mem.bought[CardName.MILITIA] = 1
    check(
        "$4 apres militia -> farming village",
        choose_buy(make_game({}, stock=empire_stock()), 4, mem),
        CardName.FARMINGVILLAGE,
    )
    mem.bought[CardName.FARMINGVILLAGE] = 1
    check(
        "$4 moteur complet -> silver",
        choose_buy(make_game({}, stock=empire_stock()), 4, mem),
        CardName.SILVER,
    )

    # Reset engine buys for greening tests
    mem.bought.clear()
    check(
        "$5 p6 duchy prioritaire",
        choose_buy(make_game({}, provinces=6, stock=empire_stock()), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 p6 gardens greening",
        choose_buy(make_game({}, provinces=6, stock=empire_stock()), 4, mem),
        CardName.GARDENS,
    )
    check(
        "$5 p5 duchy",
        choose_buy(make_game({}, provinces=5, stock=empire_stock()), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 p5 plus d'actions -> gardens",
        choose_buy(make_game({}, provinces=5, stock=empire_stock()), 4, mem),
        CardName.GARDENS,
    )
    check(
        "$5 p7 duchy (4j)",
        choose_buy(
            make_game({}, provinces=7, stock=empire_stock(), n_players=4),
            5,
            mem,
        ),
        CardName.DUCHY,
    )

    # Repli sans cartes Empire : smithy
    mem.bought.clear()
    check(
        "$4 smithy repli",
        choose_buy(
            make_game({}, stock={CardName.SMITHY: 10, CardName.CURSE: 0}),
            4,
            mem,
        ),
        CardName.SMITHY,
    )

    fv_hand = Cards(
        quantities={
            CardName.FARMINGVILLAGE: 1,
            CardName.FESTIVAL: 1,
            CardName.WITCH: 1,
        }
    )
    check(
        "joue festival (+buy/$) avant farming village",
        choose_action(fv_hand, make_game({}, stock=empire_stock())),
        CardName.FESTIVAL,
    )
    attack_hand = Cards(quantities={CardName.WITCH: 1, CardName.MILITIA: 1})
    check(
        "joue witch avant militia",
        choose_action(attack_hand, make_game({}, stock={CardName.CURSE: 10})),
        CardName.WITCH,
    )
    militia_only = Cards(quantities={CardName.MILITIA: 1, CardName.SMITHY: 1})
    check(
        "joue militia avant smithy",
        choose_action(militia_only, make_game({}, stock={CardName.CURSE: 0})),
        CardName.MILITIA,
    )

    end_game_state("t1")
    init_game("t1")
    reset_turn("t1")
    gs = make_game(
        {CardName.FESTIVAL: 1, CardName.GOLD: 1, CardName.COPPER: 2},
        stock=empire_stock(),
    )
    check("ACTION festival", decide_play(gs, "t1"), "ACTION festival")
    # gold 3 + 2 copper + festival $2 = 7 -> gold ; purchases_left=2
    check("BUY gold apres festival", decide_play(gs, "t1"), "BUY gold")

    hand_attacked = [CardName.GOLD, CardName.CURSE, CardName.ESTATE, CardName.COPPER]
    check("defausse curse", choose_discard(hand_attacked), CardName.CURSE)
    check("trash curse", choose_trash(hand_attacked, mem), CardName.CURSE)
    check("trash copper ok", confirm_trash(CardName.COPPER, hand_attacked, mem), True)
    check("trash gold no", confirm_trash(CardName.GOLD, hand_attacked, mem), False)
    check("discard estate", confirm_discard(CardName.ESTATE, hand_attacked), True)
    check(
        "gain gold > copper",
        choose_gain([CardName.COPPER, CardName.GOLD, CardName.ESTATE], mem),
        CardName.GOLD,
    )
    check("skip curse", skip_reception(CardName.CURSE, [CardName.COPPER]), True)
    check("take gold", skip_reception(CardName.GOLD, [CardName.COPPER]), False)
    check(
        "mine silver first",
        choose_money_to_upgrade([CardName.GOLD, CardName.COPPER, CardName.SILVER]),
        CardName.SILVER,
    )

    init_game("A")
    init_game("B")
    _memory("A").bought[CardName.WITCH] = 9
    check("isolation", _memory("B").bought.get(CardName.WITCH, 0), 0)

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
