from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases import GameUseCase, NotFoundError
from src.infrastructure.db.repositories import GameRepository
from src.presentation.dependencies import get_current_user, get_db_session, get_game_use_case
from src.presentation.schemas import GameCardSchema, GameCreateSchema

router = APIRouter(prefix="/api/v1/games", tags=["Games"])


@router.get("", response_model=list[GameCardSchema])
async def list_games(
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    return await GameRepository(session).list_games(query=q, limit=limit, offset=offset)


@router.get("/{game_id}", response_model=GameCardSchema)
async def get_game(game_id: UUID, use_case: GameUseCase = Depends(get_game_use_case)):
    try:
        return await use_case.get_game_card(game_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=GameCardSchema, status_code=status.HTTP_201_CREATED)
async def create_game(
    body: GameCreateSchema,
    current: tuple[UUID, str] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    _, role = current
    if role != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return await GameRepository(session).create(**body.model_dump())
