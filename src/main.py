from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from src.infrastructure.config import settings
from src.infrastructure.db.models import Base
from src.infrastructure.db.session import engine
from src.infrastructure.messaging.rabbitmq import RabbitMQEventBus
from src.presentation.routers import auth, games, moderation, reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.event_bus = RabbitMQEventBus(settings.rabbitmq_url)
    await app.state.event_bus.connect()
    try:
        yield
    finally:
        await app.state.event_bus.close()
        await app.state.redis.aclose()
        await engine.dispose()


app = FastAPI(
    title="Game Reviews & Ratings API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(games.router)
app.include_router(reviews.router)
app.include_router(moderation.router)
