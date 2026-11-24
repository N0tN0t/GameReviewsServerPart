import asyncio
from typing import Any
from uuid import UUID

from src.application.ports import CachePort, EventBusPort, ModerationFilterPort
from src.domain.services import calculate_bayesian_rating, detect_review_bombing


class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


class GameUseCase:
    def __init__(self, game_repo: Any, cache: CachePort) -> None:
        self._games = game_repo
        self._cache = cache

    async def get_game_card(self, game_id: UUID) -> dict[str, Any]:
        cached = await self._cache.get_game_card(game_id)
        if cached is not None:
            return cached

        if not await self._cache.acquire_stampede_lock(game_id):
            await asyncio.sleep(0.05)
            cached_retry = await self._cache.get_game_card(game_id)
            if cached_retry is not None:
                return cached_retry

        game = await self._games.get_by_id(game_id)
        if game is None:
            raise NotFoundError("Игра не найдена")

        payload = {
            "id": str(game.id),
            "slug": game.slug,
            "title": game.title,
            "description": game.description,
            "developer": game.developer,
            "release_date": game.release_date.isoformat() if game.release_date else None,
            "genres": game.genres,
            "platforms": game.platforms,
            "raw_avg_rating": float(game.raw_avg_rating),
            "bayesian_rating": float(game.bayesian_rating),
            "reviews_count": game.reviews_count,
            "under_review_bombing": game.under_review_bombing,
        }
        await self._cache.set_game_card(game_id, payload)
        return payload


class ReviewUseCase:
    def __init__(
        self,
        game_repo: Any,
        review_repo: Any,
        moderation: ModerationFilterPort,
        event_bus: EventBusPort,
    ) -> None:
        self._games = game_repo
        self._reviews = review_repo
        self._moderation = moderation
        self._event_bus = event_bus

    async def publish_or_update(
        self,
        user_id: UUID,
        game_id: UUID,
        rating: int,
        text: str,
    ) -> tuple[Any, bool]:
        game = await self._games.get_by_id(game_id)
        if game is None:
            raise NotFoundError("Игра не найдена")

        is_ok, rule_name, content_hash = await self._moderation.check_text(user_id, text)
        status = "approved" if is_ok else "rejected"

        review, is_created = await self._reviews.upsert_review(
            user_id=user_id,
            game_id=game_id,
            rating=rating,
            body=text.strip(),
            content_hash=content_hash,
            status=status,
            triggered_rule=rule_name,
        )

        if status == "approved":
            await self._event_bus.publish_review_changed(game_id)

        return review, is_created

    async def delete_review(self, review_id: UUID, actor_id: UUID, actor_role: str) -> None:
        review = await self._reviews.get_by_id(review_id)
        if review is None:
            raise NotFoundError("Отзыв не найден")

        if review.user_id != actor_id and actor_role not in ("moderator", "admin"):
            raise ForbiddenError("Недостаточно прав для удаления чужого отзыва")

        game_id = review.game_id
        await self._reviews.delete(review)
        await self._event_bus.publish_review_changed(game_id)


class RatingRecalculationUseCase:
    def __init__(self, game_repo: Any, review_repo: Any) -> None:
        self._games = game_repo
        self._reviews = review_repo

    async def recalculate_for_game(self, game_id: UUID) -> None:
        game = await self._games.get_by_id(game_id)
        if game is None:
            return

        window_ratings = await self._reviews.get_recent_hour_ratings(game_id)
        baseline_rate = await self._reviews.get_baseline_hourly_rate(game_id)
        historical_ratings = await self._reviews.get_historical_valid_ratings(game_id)

        anomaly = detect_review_bombing(
            window_ratings=window_ratings,
            baseline_hourly_rate=baseline_rate,
            historical_ratings=historical_ratings,
        )
        if anomaly:
            await self._reviews.mark_recent_hour_anomalous(game_id)

        valid_ratings = await self._reviews.get_all_valid_ratings(game_id)
        global_mean = await self._reviews.get_global_catalog_mean()
        agg = calculate_bayesian_rating(valid_ratings=valid_ratings, global_mean=global_mean)

        await self._games.update_rating_metrics(
            game_id=game_id,
            raw_avg=agg.raw_average,
            bayesian_rating=agg.bayesian_rating,
            reviews_count=agg.valid_count,
            under_review_bombing=anomaly,
        )
