from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.repositories import ReviewRepository
from src.presentation.dependencies import get_current_user, get_db_session
from src.presentation.schemas import ModerationPatchSchema, ReviewResponseSchema

router = APIRouter(prefix="/api/v1/moderation", tags=["Moderation"])


@router.patch("/reviews/{review_id}", response_model=ReviewResponseSchema)
async def moderate_review(
    review_id: UUID,
    body: ModerationPatchSchema,
    request: Request,
    current: tuple[UUID, str] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    moderator_id, role = current
    if role not in ("moderator", "admin"):
        raise HTTPException(status_code=403, detail="Требуются права модератора")

    repo = ReviewRepository(session)
    review = await repo.get_by_id(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Отзыв не найден")

    updated = await repo.moderate_manual(
        review=review,
        status=body.status,
        is_anomalous=body.is_anomalous,
        reason=body.reason,
        moderator_id=moderator_id,
    )
    await request.app.state.event_bus.publish_review_changed(updated.game_id)
    return updated
