from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases import ForbiddenError, NotFoundError, ReviewUseCase
from src.infrastructure.db.repositories import ReviewRepository
from src.presentation.dependencies import (
    get_current_user,
    get_current_user_id,
    get_db_session,
    get_review_use_case,
    rate_limit,
)
from src.presentation.schemas import ReviewResponseSchema, ReviewUpsertSchema, VoteSchema

router = APIRouter(prefix="/api/v1", tags=["Reviews"])


@router.get("/games/{game_id}/reviews", response_model=list[ReviewResponseSchema])
async def list_reviews(
    game_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    return await ReviewRepository(session).list_by_game(game_id, limit=limit, offset=offset)


@router.put(
    "/games/{game_id}/reviews",
    response_model=ReviewResponseSchema,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
)
async def upsert_game_review(
    game_id: UUID,
    body: ReviewUpsertSchema,
    response: Response,
    user_id: UUID = Depends(get_current_user_id),
    use_case: ReviewUseCase = Depends(get_review_use_case),
):
    try:
        result, is_created = await use_case.publish_or_update(
            user_id=user_id,
            game_id=game_id,
            rating=body.rating,
            text=body.text,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response.status_code = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
    return result


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: UUID,
    current: tuple[UUID, str] = Depends(get_current_user),
    use_case: ReviewUseCase = Depends(get_review_use_case),
):
    user_id, role = current
    try:
        await use_case.delete_review(review_id, user_id, role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/vote", status_code=status.HTTP_200_OK)
async def vote_review(
    review_id: UUID,
    body: VoteSchema,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
):
    repo = ReviewRepository(session)
    review = await repo.get_by_id(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Отзыв не найден")
    if review.user_id == user_id:
        raise HTTPException(status_code=400, detail="Нельзя голосовать за собственный отзыв")
    await repo.add_vote(user_id=user_id, review_id=review_id, is_helpful=body.is_helpful)
    return {"status": "ok"}
