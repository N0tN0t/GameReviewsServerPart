from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.main import app
from src.presentation.dependencies import (
    get_current_user,
    get_current_user_id,
    get_review_use_case,
)


class FakeRedis:
    async def incr(self, key: str) -> int:
        return 1

    async def expire(self, key: str, seconds: int) -> None:
        return None


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    app.state.redis = FakeRedis()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/games/{uuid4()}/reviews",
            headers={"Authorization": "Bearer wrong.jwt.token"},
            json={"rating": 9, "text": "Очень хорошая игра с отличной графикой."},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_game_forbidden_for_regular_user():
    app.dependency_overrides[get_current_user] = lambda: (uuid4(), "user")
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/games",
                headers={"Authorization": "Bearer fake"},
                json={"slug": "test-game", "title": "Test Game", "developer": "Studio"},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_review_validation_rejects_bad_rating():
    app.state.redis = FakeRedis()
    app.dependency_overrides[get_current_user_id] = lambda: uuid4()
    app.dependency_overrides[get_review_use_case] = lambda: None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/v1/games/{uuid4()}/reviews",
                headers={"Authorization": "Bearer fake"},
                json={"rating": 15, "text": "коротко"},
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upsert_review_returns_201():
    uid = uuid4()
    gid = uuid4()

    class FakeReviewUseCase:
        async def publish_or_update(self, user_id, game_id, rating, text):
            review = SimpleNamespace(
                id=uuid4(),
                game_id=game_id,
                user_id=user_id,
                rating=rating,
                body=text,
                status="approved",
                is_anomalous=False,
                helpful_count=0,
                created_at=datetime.now(UTC),
            )
            return review, True

    app.state.redis = FakeRedis()
    app.dependency_overrides[get_current_user_id] = lambda: uid
    app.dependency_overrides[get_review_use_case] = lambda: FakeReviewUseCase()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/v1/games/{gid}/reviews",
                headers={"Authorization": "Bearer fake"},
                json={"rating": 9, "text": "Отличная игра с глубокой боевой системой."},
            )
        assert resp.status_code == 201
        assert resp.json()["status"] == "approved"
    finally:
        app.dependency_overrides.clear()
