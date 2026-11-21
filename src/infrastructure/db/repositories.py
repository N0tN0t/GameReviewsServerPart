from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import (
    GameModel,
    ModerationLogModel,
    RatingSnapshotModel,
    ReviewModel,
    ReviewVoteModel,
    UserModel,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> UserModel | None:
        res = await self._session.execute(select(UserModel).where(UserModel.email == email))
        return res.scalar_one_or_none()

    async def get_by_username(self, username: str) -> UserModel | None:
        res = await self._session.execute(select(UserModel).where(UserModel.username == username))
        return res.scalar_one_or_none()

    async def create(
        self, username: str, email: str, password_hash: str, role: str = "user"
    ) -> UserModel:
        user = UserModel(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user


class GameRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, game_id: UUID) -> GameModel | None:
        res = await self._session.execute(select(GameModel).where(GameModel.id == game_id))
        return res.scalar_one_or_none()

    async def list_games(
        self, query: str | None = None, limit: int = 20, offset: int = 0
    ) -> list[GameModel]:
        stmt = (
            select(GameModel).order_by(GameModel.bayesian_rating.desc()).limit(limit).offset(offset)
        )
        if query:
            stmt = stmt.where(GameModel.title.ilike(f"%{query}%"))
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def create(self, **kwargs) -> GameModel:
        game = GameModel(**kwargs)
        self._session.add(game)
        await self._session.commit()
        await self._session.refresh(game)
        return game

    async def update_rating_metrics(
        self,
        game_id: UUID,
        raw_avg: float,
        bayesian_rating: float,
        reviews_count: int,
        under_review_bombing: bool,
    ) -> None:
        await self._session.execute(
            update(GameModel)
            .where(GameModel.id == game_id)
            .values(
                raw_avg_rating=raw_avg,
                bayesian_rating=bayesian_rating,
                reviews_count=reviews_count,
                under_review_bombing=under_review_bombing,
                updated_at=datetime.now(UTC),
            )
        )
        snapshot = RatingSnapshotModel(
            game_id=game_id,
            bayesian_rating=bayesian_rating,
            valid_reviews_count=reviews_count,
            anomaly_detected=under_review_bombing,
        )
        self._session.add(snapshot)
        await self._session.commit()


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, review_id: UUID) -> ReviewModel | None:
        res = await self._session.execute(select(ReviewModel).where(ReviewModel.id == review_id))
        return res.scalar_one_or_none()

    async def list_by_game(
        self, game_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[ReviewModel]:
        stmt = (
            select(ReviewModel)
            .where(ReviewModel.game_id == game_id, ReviewModel.status == "approved")
            .order_by(ReviewModel.helpful_count.desc(), ReviewModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def has_duplicate_hash_recent(self, content_hash: str) -> bool:
        since = datetime.now(UTC) - timedelta(hours=24)
        stmt = (
            select(ReviewModel.id)
            .where(
                ReviewModel.content_hash == content_hash,
                ReviewModel.created_at >= since,
            )
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def upsert_review(
        self,
        user_id: UUID,
        game_id: UUID,
        rating: int,
        body: str,
        content_hash: str,
        status: str,
        triggered_rule: str,
    ) -> tuple[ReviewModel, bool]:
        stmt = select(ReviewModel).where(
            ReviewModel.user_id == user_id,
            ReviewModel.game_id == game_id,
        )
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        is_created = existing is None
        if existing is None:
            review = ReviewModel(
                user_id=user_id,
                game_id=game_id,
                rating=rating,
                body=body,
                content_hash=content_hash,
                status=status,
            )
            self._session.add(review)
            await self._session.flush()
        else:
            existing.rating = rating
            existing.body = body
            existing.content_hash = content_hash
            existing.status = status
            existing.updated_at = datetime.now(UTC)
            review = existing

        log = ModerationLogModel(
            review_id=review.id,
            decision=status,
            triggered_rule=triggered_rule,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(review)
        return review, is_created

    async def moderate_manual(
        self,
        review: ReviewModel,
        status: str,
        is_anomalous: bool,
        reason: str,
        moderator_id: UUID,
    ) -> ReviewModel:
        review.status = status
        review.is_anomalous = is_anomalous
        review.updated_at = datetime.now(UTC)
        log = ModerationLogModel(
            review_id=review.id,
            decision=status,
            triggered_rule=reason,
            moderator_id=moderator_id,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(review)
        return review

    async def delete(self, review: ReviewModel) -> None:
        await self._session.delete(review)
        await self._session.commit()

    async def add_vote(self, user_id: UUID, review_id: UUID, is_helpful: bool) -> None:
        existing = await self._session.execute(
            select(ReviewVoteModel).where(
                ReviewVoteModel.user_id == user_id,
                ReviewVoteModel.review_id == review_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        self._session.add(
            ReviewVoteModel(user_id=user_id, review_id=review_id, is_helpful=is_helpful)
        )
        if is_helpful:
            await self._session.execute(
                update(ReviewModel)
                .where(ReviewModel.id == review_id)
                .values(helpful_count=ReviewModel.helpful_count + 1)
            )
        await self._session.commit()

    async def get_recent_hour_ratings(self, game_id: UUID) -> list[int]:
        since = datetime.now(UTC) - timedelta(hours=1)
        stmt = select(ReviewModel.rating).where(
            ReviewModel.game_id == game_id,
            ReviewModel.status == "approved",
            ReviewModel.created_at >= since,
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_baseline_hourly_rate(self, game_id: UUID) -> float:
        since_week = datetime.now(UTC) - timedelta(days=7)
        until_hour = datetime.now(UTC) - timedelta(hours=1)
        stmt = select(func.count(ReviewModel.id)).where(
            ReviewModel.game_id == game_id,
            ReviewModel.status == "approved",
            ReviewModel.created_at >= since_week,
            ReviewModel.created_at < until_hour,
        )
        res = await self._session.execute(stmt)
        total = res.scalar_one() or 0
        return total / (7 * 24 - 1)

    async def get_historical_valid_ratings(self, game_id: UUID) -> list[int]:
        until_hour = datetime.now(UTC) - timedelta(hours=1)
        stmt = select(ReviewModel.rating).where(
            ReviewModel.game_id == game_id,
            ReviewModel.status == "approved",
            ReviewModel.is_anomalous.is_(False),
            ReviewModel.created_at < until_hour,
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def mark_recent_hour_anomalous(self, game_id: UUID) -> None:
        since = datetime.now(UTC) - timedelta(hours=1)
        await self._session.execute(
            update(ReviewModel)
            .where(
                ReviewModel.game_id == game_id,
                ReviewModel.created_at >= since,
                ReviewModel.rating.in_([1, 10]),
            )
            .values(is_anomalous=True)
        )
        await self._session.commit()

    async def get_all_valid_ratings(self, game_id: UUID) -> list[int]:
        stmt = select(ReviewModel.rating).where(
            ReviewModel.game_id == game_id,
            ReviewModel.status == "approved",
            ReviewModel.is_anomalous.is_(False),
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_global_catalog_mean(self) -> float:
        stmt = select(func.avg(ReviewModel.rating)).where(
            ReviewModel.status == "approved",
            ReviewModel.is_anomalous.is_(False),
        )
        res = await self._session.execute(stmt)
        avg = res.scalar_one()
        return float(avg) if avg is not None else 7.0
