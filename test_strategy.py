"""Tests stratégie adaptative au kingdom."""

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
    check("$5 bandit avant market", choose_buy(g_m, 5, mem), CardName.BANDIT)
    check("$4 port", choose_buy(g_m, 4, mem), CardName.PORT)
    check(
        "$6 witch avant or",
        choose_buy(
            make_game({}, stock={CardName.WITCH: 10, CardName.GOLD: 30}),
            6,
            mem,
        ),
        CardName.WITCH,
    )
    check(
        "$4 milice avant port",
        choose_buy(
            make_game({}, stock={CardName.MILITIA: 10, CardName.PORT: 10}),
            4,
            mem,
        ),
        CardName.MILITIA,
    )
    check(
        "$4 port plutot que bureaucrate",
        choose_buy(make_game({}, stock={CardName.BUREAUCRAT: 10, CardName.PORT: 10}), 4, mem),
        CardName.PORT,
    )
    check(
        "$4 p4 pas de jardins -> silver",
        choose_buy(make_game({}, provinces=4, stock={CardName.GARDENS: 10}), 4, mem),
        CardName.SILVER,
    )
    check(
        "$3 chapelle si sorciere",
        choose_buy(
            make_game({}, stock={CardName.WITCH: 10, CardName.CHAPEL: 10}),
            3,
            mem,
        ),
        CardName.CHAPEL,
    )
    check(
        "$4 preteur avant forgeron sans chapelle",
        choose_buy(
            make_game(
                {},
                stock={
                    CardName.WITCH: 10,
                    CardName.MONEYLENDER: 10,
                    CardName.SMITHY: 10,
                },
            ),
            4,
            mem,
        ),
        CardName.MONEYLENDER,
    )
    mem.bought[CardName.WITCH] = 1
    check(
        "$6 une seule sorciere puis or",
        choose_buy(
            make_game({}, stock={CardName.WITCH: 10, CardName.GOLD: 30}),
            6,
            mem,
        ),
        CardName.GOLD,
    )
    mem.bought.pop(CardName.WITCH, None)

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

    # Hooks : on ne jette jamais l'Or en premier, on prend l'attaque offerte
    hand_attacked = [CardName.GOLD, CardName.CURSE, CardName.ESTATE, CardName.COPPER]
    check("milice defausse malediction", choose_discard(hand_attacked), CardName.CURSE)
    check("renovation ecarte malediction", choose_trash(hand_attacked, mem), CardName.CURSE)
    check("chapelle ecarte cuivre", confirm_trash(CardName.COPPER, hand_attacked, mem), True)
    check("chapelle garde or", confirm_trash(CardName.GOLD, hand_attacked, mem), False)
    check("cave defausse domaine", confirm_discard(CardName.ESTATE, hand_attacked), True)
    check("cave garde or", confirm_discard(CardName.GOLD, hand_attacked), False)
    check(
        "gain sorciere plutot que cuivre",
        choose_gain([CardName.COPPER, CardName.WITCH, CardName.ESTATE], mem),
        CardName.WITCH,
    )
    check(
        "bibliotheque refuse malediction",
        skip_reception(CardName.CURSE, [CardName.COPPER]),
        True,
    )
    check(
        "bibliotheque prend or",
        skip_reception(CardName.GOLD, [CardName.COPPER]),
        False,
    )
    check(
        "mine ameliore argent avant or",
        choose_money_to_upgrade([CardName.GOLD, CardName.COPPER, CardName.SILVER]),
        CardName.SILVER,
    )

    # Sorcière jouée avant Bandit s'il reste des malédictions
    attack_hand = Cards(quantities={CardName.WITCH: 1, CardName.BANDIT: 1, CardName.SMITHY: 1})
    check(
        "joue witch avant bandit",
        choose_action(attack_hand, make_game({}, stock={CardName.CURSE: 10})),
        CardName.WITCH,
    )

    init_game("A")
    init_game("B")
    _memory("A").bought[CardName.MARKET] = 9
    check("isolation", _memory("B").bought.get(CardName.MARKET, 0), 0)

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
