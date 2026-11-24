import json
import random
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis


class RedisGameCache:
    def __init__(self, client: aioredis.Redis, base_ttl: int = 300) -> None:
        self._redis = client
        self._base_ttl = base_ttl

    @staticmethod
    def _card_key(game_id: UUID) -> str:
        return f"game:card:{game_id}"

    async def get_game_card(self, game_id: UUID) -> dict[str, Any] | None:
        raw = await self._redis.get(self._card_key(game_id))
        return json.loads(raw) if raw else None

    async def set_game_card(self, game_id: UUID, payload: dict[str, Any]) -> None:
        jitter = random.randint(0, int(self._base_ttl * 0.2))
        await self._redis.setex(
            self._card_key(game_id),
            self._base_ttl + jitter,
            json.dumps(payload, ensure_ascii=False),
        )

    async def acquire_stampede_lock(self, game_id: UUID) -> bool:
        return bool(await self._redis.set(f"lock:game:{game_id}", "1", ex=5, nx=True))

    async def invalidate_game(self, game_id: UUID) -> None:
        await self._redis.delete(self._card_key(game_id))


class RedisRateLimiter:
    def __init__(self, client: aioredis.Redis) -> None:
        self._redis = client

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, window_seconds)
        return count <= max_requests
