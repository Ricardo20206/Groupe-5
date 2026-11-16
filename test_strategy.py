"""Tests stratégie adaptative : 3 plans + greening selon joueurs."""

from __future__ import annotations

from dopynion.data_model import CardName, Cards, Game, Player

from strategy import (
    Plan,
    choose_action,
    choose_buy,
    choose_discard,
    choose_gain,
    choose_money_to_upgrade,
    choose_trash,
    confirm_discard,
    confirm_trash,
    decide_play,
    detect_plan,
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

    # Kingdom sans actions moteur -> Big Money
    g_bm = make_game({})
    check("plan BM", detect_plan(g_bm, mem), Plan.BIG_MONEY)
    check("$3 BM silver", choose_buy(g_bm, 3, mem), CardName.SILVER)
    check("$6 BM gold", choose_buy(g_bm, 6, mem), CardName.GOLD)
    check("$8 BM province", choose_buy(g_bm, 8, mem), CardName.PROVINCE)

    # Kingdom avec Hireling
    g_h = make_game({}, stock={CardName.HIRELING: 10})
    check("$6 hireling", choose_buy(g_h, 6, mem), CardName.HIRELING)

    # Plan ENGINE : market/port/magpie (+ bandit ignoré)
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
    check("plan engine", detect_plan(g_m, mem), Plan.ENGINE)
    check("$5 engine market pas bandit", choose_buy(g_m, 5, mem), CardName.MARKET)
    check("$4 engine port", choose_buy(g_m, 4, mem), CardName.PORT)

    # Plan WITCH
    check(
        "plan witch",
        detect_plan(make_game({}, stock={CardName.WITCH: 10}), mem),
        Plan.WITCH,
    )
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

    # Plan ATTACK : milice/bandit sans gros moteur
    g_atk = make_game({}, stock={CardName.MILITIA: 10, CardName.PORT: 10})
    check("plan attack", detect_plan(g_atk, mem), Plan.ATTACK)
    check("$4 milice avant port", choose_buy(g_atk, 4, mem), CardName.MILITIA)
    check(
        "$5 bandit si pas de moteur fort",
        choose_buy(
            make_game({}, stock={CardName.BANDIT: 10, CardName.SMITHY: 10}),
            5,
            mem,
        ),
        CardName.BANDIT,
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

    mem.bought[CardName.WITCH] = 1
    check(
        "$6 sorciere seule sans village -> or",
        choose_buy(
            make_game({}, stock={CardName.WITCH: 10, CardName.GOLD: 30}),
            6,
            mem,
        ),
        CardName.GOLD,
    )
    check(
        "$4 apres sorciere -> port pas milice",
        choose_buy(
            make_game({}, stock={CardName.MILITIA: 10, CardName.PORT: 10, CardName.WITCH: 10}),
            4,
            mem,
        ),
        CardName.PORT,
    )
    mem.bought[CardName.VILLAGE] = 1
    check(
        "$5 2e sorciere si village",
        choose_buy(
            make_game({}, stock={CardName.WITCH: 10, CardName.MARKET: 10}),
            5,
            mem,
        ),
        CardName.WITCH,
    )
    mem.bought.pop(CardName.WITCH, None)
    mem.bought.pop(CardName.VILLAGE, None)

    # Witch si malédictions ; sans curse -> moteur
    g_w = make_game({}, stock={CardName.WITCH: 10, CardName.MARKET: 10})
    check("$5 witch avant market", choose_buy(g_w, 5, mem), CardName.WITCH)
    g_nocurse = make_game(
        {},
        stock={CardName.WITCH: 10, CardName.MARKET: 10, CardName.CURSE: 0},
    )
    check("$5 sans curse -> market", choose_buy(g_nocurse, 5, mem), CardName.MARKET)

    # Greening : 2 joueurs = duché à <=5, stop actions à <=4
    check(
        "$5 p5 duchy (2j)",
        choose_buy(make_game({}, provinces=5, stock={CardName.MARKET: 10}), 5, mem),
        CardName.DUCHY,
    )
    check(
        "$4 p4 stop actions -> silver (2j)",
        choose_buy(make_game({}, provinces=4, stock={CardName.PORT: 10}), 4, mem),
        CardName.SILVER,
    )
    # 4 joueurs : duché dès 7 Provinces, stop actions à 6
    check(
        "$5 p7 duchy (4j)",
        choose_buy(
            make_game({}, provinces=7, stock={CardName.MARKET: 10}, n_players=4),
            5,
            mem,
        ),
        CardName.DUCHY,
    )
    check(
        "$4 p6 stop actions (4j)",
        choose_buy(
            make_game({}, provinces=6, stock={CardName.PORT: 10}, n_players=4),
            4,
            mem,
        ),
        CardName.SILVER,
    )

    # Actions : +actions d'abord, Chapelle si rebut
    hand = Cards(
        quantities={CardName.MARKET: 1, CardName.SMITHY: 1, CardName.COPPER: 1}
    )
    check(
        "market avant smithy",
        choose_action(hand, make_game({}, stock={CardName.MARKET: 1, CardName.SMITHY: 1})),
        CardName.MARKET,
    )
    chapel_hand = Cards(
        quantities={
            CardName.CHAPEL: 1,
            CardName.WITCH: 1,
            CardName.CURSE: 1,
            CardName.COPPER: 1,
        }
    )
    check(
        "chapelle avant witch si malediction",
        choose_action(chapel_hand, make_game({}, stock={CardName.CURSE: 10})),
        CardName.CHAPEL,
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
    check("BUY port", decide_play(gs, "t1"), "BUY port")
    check("END_TURN", decide_play(gs, "t1"), "END_TURN")

    # Hooks
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

    attack_hand = Cards(quantities={CardName.WITCH: 1, CardName.BANDIT: 1, CardName.SMITHY: 1})
    check(
        "joue witch avant bandit",
        choose_action(attack_hand, make_game({}, stock={CardName.CURSE: 10})),
        CardName.WITCH,
    )

    # Plan ATTACK : une seule attaque puis Or
    init_game("atk")
    mem_atk = _memory("atk")
    mem_atk.bought[CardName.BANDIT] = 1
    check(
        "$5 apres 1 bandit -> plus d'attaque",
        choose_buy(
            make_game({}, stock={CardName.BANDIT: 10, CardName.MILITIA: 10, CardName.GOLD: 30}),
            5,
            mem_atk,
        ),
        CardName.SILVER,
    )
    check(
        "$6 apres 1 bandit -> or",
        choose_buy(
            make_game({}, stock={CardName.BANDIT: 10, CardName.MILITIA: 10, CardName.GOLD: 30}),
            6,
            mem_atk,
        ),
        CardName.GOLD,
    )

    init_game("A")
    init_game("B")
    _memory("A").bought[CardName.MARKET] = 9
    check("isolation", _memory("B").bought.get(CardName.MARKET, 0), 0)

    print("Tous les tests OK.")


if __name__ == "__main__":
    main()
