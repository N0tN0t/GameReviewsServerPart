from collections.abc import AsyncGenerator
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases import GameUseCase, ReviewUseCase
from src.infrastructure.cache.redis_cache import RedisGameCache, RedisRateLimiter
from src.infrastructure.db.repositories import GameRepository, ReviewRepository
from src.infrastructure.db.session import async_session_factory
from src.infrastructure.moderation.text_filter import SimpleTextModerationFilter
from src.infrastructure.security import decode_access_token

bearer_scheme = HTTPBearer()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def get_cache(request: Request) -> RedisGameCache:
    return RedisGameCache(request.app.state.redis)


def get_game_use_case(
    session: AsyncSession = Depends(get_db_session),
    cache: RedisGameCache = Depends(get_cache),
) -> GameUseCase:
    return GameUseCase(GameRepository(session), cache)


def get_review_use_case(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ReviewUseCase:
    review_repo = ReviewRepository(session)
    return ReviewUseCase(
        game_repo=GameRepository(session),
        review_repo=review_repo,
        moderation=SimpleTextModerationFilter(review_repo),
        event_bus=request.app.state.event_bus,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> tuple[UUID, str]:
    try:
        payload = decode_access_token(credentials.credentials)
        return UUID(payload["sub"]), str(payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен авторизации",
        ) from exc


def get_current_user_id(current: tuple[UUID, str] = Depends(get_current_user)) -> UUID:
    return current[0]


def rate_limit(max_requests: int, window_seconds: int):
    async def _limiter(request: Request) -> None:
        limiter = RedisRateLimiter(request.app.state.redis)
        client_ip = request.client.host if request.client else "unknown"
        key = f"rl:{request.url.path}:{client_ip}"
        if not await limiter.is_allowed(key, max_requests, window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Превышен лимит запросов, попробуйте позже",
            )

    return _limiter
