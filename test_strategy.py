"""Tests stratégie adaptative top-Elo."""

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


def stock(extra: dict[CardName, int] | None = None) -> dict[CardName, int]:
    base = {
        CardName.MILITIA: 10,
        CardName.WITCH: 10,
        CardName.FARMINGVILLAGE: 10,
        CardName.FESTIVAL: 10,
        CardName.VILLAGE: 10,
        CardName.LABORATORY: 10,
        CardName.SMITHY: 10,
        CardName.BANDIT: 10,
        CardName.HIRELING: 10,
        CardName.CHAPEL: 10,
        CardName.MARKET: 10,
        CardName.GARDENS: 12,
    }
    if extra:
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
        "$5 witch",
        choose_buy(make_game({}, stock=stock()), 5, mem),
        CardName.WITCH,
    )
    mem.bought[CardName.WITCH] = 2
    check(
        "$5 apres witches -> festival",
        choose_buy(make_game({}, stock=stock()), 5, mem),
        CardName.FESTIVAL,
    )
    mem.bought.clear()
    check(
        "$4 militia",
        choose_buy(make_game({}, stock=stock()), 4, mem),
        CardName.MILITIA,
    )
    mem.bought[CardName.MILITIA] = 1
    mem.bought[CardName.WITCH] = 1
    check(
        "$4 village apres terminale",
        choose_buy(make_game({}, stock=stock()), 4, mem),
        CardName.FARMINGVILLAGE,
    )

    mem.bought.clear()
    check(
        "$6 or prioritaire (pas hireling)",
        choose_buy(make_game({}, stock=stock()), 6, mem),
        CardName.GOLD,
    )
    mem.bought[CardName.GOLD] = 2
    check(
        "$6 hireling si or epuise et 2 or",
        choose_buy(
            make_game({}, stock=stock({CardName.GOLD: 0})),
            6,
            mem,
        ),
        CardName.HIRELING,
    )
    check(
        "$11 pas de colonie -> province",
        choose_buy(
            make_game({}, stock=stock({CardName.COLONY: 10})),
            11,
            mem,
        ),
        CardName.PROVINCE,
    )

    mem.bought.clear()
    check(
        "$5 p6 duchy",
        choose_buy(make_game({}, provinces=6, stock=stock()), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 p6 gardens",
        choose_buy(make_game({}, provinces=6, stock=stock()), 4, mem),
        CardName.GARDENS,
    )
    check(
        "$2 chapel si witch kingdom",
        choose_buy(make_game({}, stock=stock()), 2, mem),
        CardName.CHAPEL,
    )

    # Smithy si pas de witch au kingdom
    mem.bought.clear()
    check(
        "$4 smithy sans witch pile",
        choose_buy(
            make_game(
                {},
                stock={
                    CardName.SMITHY: 10,
                    CardName.MILITIA: 0,
                    CardName.FARMINGVILLAGE: 0,
                    CardName.PORT: 0,
                    CardName.VILLAGE: 0,
                    CardName.BUREAUCRAT: 0,
                },
            ),
            4,
            mem,
        ),
        CardName.SMITHY,
    )

    chapel_hand = Cards(
        quantities={CardName.CHAPEL: 1, CardName.COPPER: 2, CardName.WITCH: 1}
    )
    check(
        "joue chapel avec copper",
        choose_action(chapel_hand, make_game({}, stock=stock())),
        CardName.CHAPEL,
    )

    fv_hand = Cards(
        quantities={
            CardName.FESTIVAL: 1,
            CardName.FARMINGVILLAGE: 1,
            CardName.WITCH: 1,
        }
    )
    check(
        "festival avant farming village",
        choose_action(fv_hand, make_game({}, stock=stock())),
        CardName.FESTIVAL,
    )
    check(
        "witch avant militia",
        choose_action(
            Cards(quantities={CardName.WITCH: 1, CardName.MILITIA: 1}),
            make_game({}, stock={CardName.CURSE: 10}),
        ),
        CardName.WITCH,
    )

    end_game_state("t1")
    init_game("t1")
    reset_turn("t1")
    gs = make_game(
        {CardName.FESTIVAL: 1, CardName.GOLD: 1, CardName.COPPER: 2},
        stock=stock(),
    )
    check("ACTION festival", decide_play(gs, "t1"), "ACTION festival")
    check("BUY gold", decide_play(gs, "t1"), "BUY gold")

    # Anti-crash : decide_play ne doit jamais lever
    end_game_state("bad")
    init_game("bad")
    reset_turn("bad")
    check(
        "crash safe END_TURN",
        decide_play(make_game({CardName.COPPER: 1}), "bad")
        in ("END_TURN", "BUY silver", "BUY chapel"),
        True,
    )

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
