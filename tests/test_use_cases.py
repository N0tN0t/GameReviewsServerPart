from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.use_cases import GameUseCase, ReviewUseCase


class FakeCache:
    def __init__(self) -> None:
        self.store = {}

    async def get_game_card(self, game_id):
        return self.store.get(game_id)

    async def set_game_card(self, game_id, payload):
        self.store[game_id] = payload

    async def acquire_stampede_lock(self, game_id):
        return True

    async def invalidate_game(self, game_id):
        self.store.pop(game_id, None)


class FakeGameRepo:
    def __init__(self, game) -> None:
        self.game = game
        self.calls = 0

    async def get_by_id(self, game_id):
        self.calls += 1
        return self.game if self.game and self.game.id == game_id else None


class FakeEventBus:
    def __init__(self) -> None:
        self.published = []

    async def publish_review_changed(self, game_id):
        self.published.append(game_id)


@pytest.mark.asyncio
async def test_game_use_case_uses_cache_aside():
    gid = uuid4()
    game = SimpleNamespace(
        id=gid,
        slug="witcher-3",
        title="The Witcher 3",
        description="RPG",
        developer="CDPR",
        release_date=date(2015, 5, 19),
        genres=["RPG"],
        platforms=["PC"],
        raw_avg_rating=9.5,
        bayesian_rating=9.4,
        reviews_count=100,
        under_review_bombing=False,
    )
    repo = FakeGameRepo(game)
    cache = FakeCache()
    uc = GameUseCase(repo, cache)

    first = await uc.get_game_card(gid)
    second = await uc.get_game_card(gid)

    assert first["title"] == "The Witcher 3"
    assert second == first
    assert repo.calls == 1


@pytest.mark.asyncio
async def test_review_use_case_publishes_only_approved():
    gid = uuid4()
    uid = uuid4()
    game = SimpleNamespace(id=gid)

    class FakeReviewRepo:
        async def upsert_review(self, **kwargs):
            return SimpleNamespace(status=kwargs["status"]), True

    class FakeModeration:
        def __init__(self, ok: bool) -> None:
            self.ok = ok

        async def check_text(self, user_id, text):
            return self.ok, "rule", "hash"

    bus_ok = FakeEventBus()
    uc_ok = ReviewUseCase(FakeGameRepo(game), FakeReviewRepo(), FakeModeration(True), bus_ok)
    await uc_ok.publish_or_update(uid, gid, 9, "Отличная игра с хорошим сюжетом")
    assert bus_ok.published == [gid]

    bus_bad = FakeEventBus()
    uc_bad = ReviewUseCase(FakeGameRepo(game), FakeReviewRepo(), FakeModeration(False), bus_bad)
    await uc_bad.publish_or_update(uid, gid, 1, "Спам ссылка https://bad.test")
    assert bus_bad.published == []
