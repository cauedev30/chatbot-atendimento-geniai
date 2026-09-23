from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from geniai.api.auth import require_login
from geniai.api.deps import app_deps, require_json
from geniai.api.schemas import Board, CategoryIn, ErrorOut, MoveIn, TakeIn
from geniai.app.board import load_board, move_card, recategorize, take_card

router = APIRouter(prefix="/api/board", tags=["board"], dependencies=[Depends(require_login)])

TicketId = Annotated[int, Path(gt=0)]
REFUSED: dict[int | str, dict[str, object]] = {400: {"model": ErrorOut}, 401: {"model": ErrorOut}}


@router.get("", responses={401: {"model": ErrorOut}})
async def get_board(request: Request) -> Board:
    return await load_board(app_deps(request))


@router.post("/tickets/{ticket_id}/move", status_code=204, responses=REFUSED, dependencies=[Depends(require_json)])
async def move(ticket_id: TicketId, body: MoveIn, request: Request) -> None:
    await move_card(app_deps(request), ticket_id, body.to)


@router.post("/tickets/{ticket_id}/take", status_code=204, responses=REFUSED, dependencies=[Depends(require_json)])
async def take(ticket_id: TicketId, body: TakeIn, request: Request) -> None:
    await take_card(app_deps(request), ticket_id, body.responsible_id)


@router.post("/tickets/{ticket_id}/category", status_code=204, responses=REFUSED, dependencies=[Depends(require_json)])
async def set_category(ticket_id: TicketId, body: CategoryIn, request: Request) -> None:
    await recategorize(app_deps(request), ticket_id, body.category_id)


@router.post("/tickets/{ticket_id}/close", status_code=204, responses=REFUSED, dependencies=[Depends(require_json)])
async def close(ticket_id: TicketId, request: Request) -> None:
    await move_card(app_deps(request), ticket_id, "resolved_by_human")
