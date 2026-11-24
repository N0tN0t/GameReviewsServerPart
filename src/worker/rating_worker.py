import asyncio
import json
from uuid import UUID

import aio_pika
import redis.asyncio as aioredis

from src.application.use_cases import RatingRecalculationUseCase
from src.infrastructure.cache.redis_cache import RedisGameCache
from src.infrastructure.config import settings
from src.infrastructure.db.repositories import GameRepository, ReviewRepository
from src.infrastructure.db.session import async_session_factory
from src.infrastructure.messaging.rabbitmq import declare_topology


async def main() -> None:
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    cache_adapter = RedisGameCache(redis_client)

    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    queue = await declare_topology(channel)

    async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            payload = json.loads(message.body.decode("utf-8"))
            game_id = UUID(payload["game_id"])
            async with async_session_factory() as session:
                use_case = RatingRecalculationUseCase(
                    game_repo=GameRepository(session),
                    review_repo=ReviewRepository(session),
                )
                await use_case.recalculate_for_game(game_id)
            await cache_adapter.invalidate_game(game_id)

    await queue.consume(on_message)
    try:
        await asyncio.Future()
    finally:
        await connection.close()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
