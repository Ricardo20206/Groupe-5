import html
import logging
from pathlib import Path
from typing import Annotated

from dopynion.data_model import (
    CardName,
    CardNameAndHand,
    Game,
    Hand,
    MoneyCardsInHand,
    PossibleCards,
)
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from strategy import (
    PLAYER_NAME,
    choose_discard,
    choose_gain,
    choose_money_to_upgrade,
    choose_trash,
    confirm_discard,
    confirm_discard_deck,
    confirm_trash,
    decide_play,
    end_game_state,
    init_game,
    reset_turn,
    skip_reception,
    _memory,
)

logging.basicConfig(level=logging.INFO)
app = FastAPI()

#############################################################################################################
# Data model for responses
#############################################################################################################


class DopynionResponseBool(BaseModel):
    game_id: str
    decision: bool


class DopynionResponseCardName(BaseModel):
    game_id: str
    decision: CardName


class DopynionResponseStr(BaseModel):
    game_id: str
    decision: str


#############################################################################################################
# Getter for the game identifier
#############################################################################################################


def get_game_id(x_game_id: str = Header(description="ID of the game")) -> str:
    return x_game_id


GameIdDependency = Annotated[str, Depends(get_game_id)]


#############################################################################################################
# Error management
#############################################################################################################


@app.exception_handler(Exception)
def unknown_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    print(exc.__class__.__name__, str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "message": "Oops!",
            "detail": str(exc),
            "name": exc.__class__.__name__,
        },
    )


#############################################################################################################
# Template extra bonus
#############################################################################################################


# The root of the website shows the code of the website
@app.get("/", response_class=HTMLResponse)
def root() -> str:
    header = (
        "<html><head><title>Dopynion template</title></head><body>"
        "<h1>Dopynion documentation</h1>"
        "<h2>API documentation</h2>"
        '<p><a href="/docs">Read the documentation.</a></p>'
        "<h2>Code template</h2>"
        "<p>The code of this website is:</p>"
        "<pre>"
    )
    footer = "</pre></body></html>"
    return header + html.escape(Path(__file__).read_text(encoding="utf-8")) + footer


#############################################################################################################
# The code of the strategy
#############################################################################################################


@app.get("/name")
def name() -> str:
    return PLAYER_NAME


@app.get("/start_game")
def start_game(game_id: GameIdDependency) -> DopynionResponseStr:
    init_game(game_id)
    return DopynionResponseStr(game_id=game_id, decision="OK")


@app.get("/start_turn")
def start_turn(game_id: GameIdDependency) -> DopynionResponseStr:
    reset_turn(game_id)
    return DopynionResponseStr(game_id=game_id, decision="OK")


@app.post("/play")
def play(game: Game, game_id: GameIdDependency) -> DopynionResponseStr:
    decision = decide_play(game, game_id)
    return DopynionResponseStr(game_id=game_id, decision=decision)


@app.get("/end_game")
def end_game(game_id: GameIdDependency) -> DopynionResponseStr:
    end_game_state(game_id)
    return DopynionResponseStr(game_id=game_id, decision="OK")


@app.post("/confirm_discard_card_from_hand")
async def confirm_discard_card_from_hand(
    game_id: GameIdDependency,
    decision_input: CardNameAndHand,
) -> DopynionResponseBool:
    decision = confirm_discard(decision_input.card_name, decision_input.hand)
    return DopynionResponseBool(game_id=game_id, decision=decision)


@app.post("/discard_card_from_hand")
async def discard_card_from_hand(
    game_id: GameIdDependency,
    decision_input: Hand,
) -> DopynionResponseCardName:
    decision = choose_discard(decision_input.hand)
    return DopynionResponseCardName(game_id=game_id, decision=decision)


@app.post("/confirm_trash_card_from_hand")
async def confirm_trash_card_from_hand(
    game_id: GameIdDependency,
    decision_input: CardNameAndHand,
) -> DopynionResponseBool:
    decision = confirm_trash(
        decision_input.card_name,
        decision_input.hand,
        _memory(game_id),
    )
    return DopynionResponseBool(game_id=game_id, decision=decision)


@app.post("/trash_card_from_hand")
async def trash_card_from_hand(
    game_id: GameIdDependency,
    decision_input: Hand,
) -> DopynionResponseCardName:
    decision = choose_trash(decision_input.hand, _memory(game_id))
    return DopynionResponseCardName(game_id=game_id, decision=decision)


@app.post("/confirm_discard_deck")
async def confirm_discard_deck_route(
    game_id: GameIdDependency,
) -> DopynionResponseBool:
    return DopynionResponseBool(game_id=game_id, decision=confirm_discard_deck())


@app.post("/choose_card_to_receive_in_discard")
async def choose_card_to_receive_in_discard(
    game_id: GameIdDependency,
    decision_input: PossibleCards,
) -> DopynionResponseCardName:
    decision = choose_gain(decision_input.possible_cards, _memory(game_id))
    return DopynionResponseCardName(game_id=game_id, decision=decision)


@app.post("/choose_card_to_receive_in_deck")
async def choose_card_to_receive_in_deck(
    game_id: GameIdDependency,
    decision_input: PossibleCards,
) -> DopynionResponseCardName:
    decision = choose_gain(decision_input.possible_cards, _memory(game_id))
    return DopynionResponseCardName(game_id=game_id, decision=decision)


@app.post("/skip_card_reception_in_hand")
async def skip_card_reception_in_hand(
    game_id: GameIdDependency,
    decision_input: CardNameAndHand,
) -> DopynionResponseBool:
    decision = skip_reception(decision_input.card_name, decision_input.hand)
    return DopynionResponseBool(game_id=game_id, decision=decision)


@app.post("/trash_money_card_for_better_money_card")
async def trash_money_card_for_better_money_card(
    game_id: GameIdDependency,
    decision_input: MoneyCardsInHand,
) -> DopynionResponseCardName:
    decision = choose_money_to_upgrade(decision_input.money_in_hand)
    return DopynionResponseCardName(game_id=game_id, decision=decision)
