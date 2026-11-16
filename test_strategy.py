"""Tests Big Money dur."""

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
        choose_buy(make_game({}, stock={CardName.WITCH: 10}), 6, mem),
        CardName.GOLD,
    )
    check(
        "$5 witch si curse",
        choose_buy(make_game({}, stock={CardName.WITCH: 10, CardName.SMITHY: 10}), 5, mem),
        CardName.WITCH,
    )
    check(
        "$5 smithy sans curse",
        choose_buy(
            make_game({}, stock={CardName.WITCH: 10, CardName.SMITHY: 10, CardName.CURSE: 0}),
            5,
            mem,
        ),
        CardName.SMITHY,
    )
    mem.bought[CardName.SMITHY] = 1
    check(
        "$5 smithy deja pris -> silver (ignore market)",
        choose_buy(
            make_game({}, stock={CardName.SMITHY: 10, CardName.MARKET: 10, CardName.CURSE: 0}),
            5,
            mem,
        ),
        CardName.SILVER,
    )
    mem.bought.pop(CardName.SMITHY, None)

    check(
        "$5 p6 duchy (2j)",
        choose_buy(make_game({}, provinces=6, stock={CardName.WITCH: 10}), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$5 p5 stop witch -> duchy or nothing special",
        choose_buy(make_game({}, provinces=5, stock={CardName.WITCH: 10}), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 p5 stop actions -> silver",
        choose_buy(make_game({}, provinces=5, stock={CardName.SMITHY: 10}), 4, mem),
        CardName.SILVER,
    )
    check(
        "$5 p7 duchy (4j)",
        choose_buy(
            make_game({}, provinces=7, stock={CardName.WITCH: 10}, n_players=4),
            5,
            mem,
        ),
        CardName.DUCHY,
    )

    hand = Cards(quantities={CardName.SMITHY: 1, CardName.COPPER: 2, CardName.SILVER: 1})
    check(
        "joue smithy",
        choose_action(hand, make_game({}, stock={CardName.SMITHY: 1})),
        CardName.SMITHY,
    )
    attack_hand = Cards(quantities={CardName.WITCH: 1, CardName.SMITHY: 1})
    check(
        "joue witch avant smithy",
        choose_action(attack_hand, make_game({}, stock={CardName.CURSE: 10})),
        CardName.WITCH,
    )

    end_game_state("t1")
    init_game("t1")
    reset_turn("t1")
    gs = make_game(
        {CardName.SMITHY: 1, CardName.GOLD: 1, CardName.COPPER: 2},
        stock={CardName.SMITHY: 10},
    )
    check("ACTION smithy", decide_play(gs, "t1"), "ACTION smithy")
    # gold 3 + 2 copper = 5 -> witch absent, smithy already in hand played, buy? smithy under cap
    check("BUY smithy or silver", decide_play(gs, "t1") in ("BUY smithy", "BUY silver"), True)

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
    _memory("A").bought[CardName.SMITHY] = 9
    check("isolation", _memory("B").bought.get(CardName.SMITHY, 0), 0)

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
