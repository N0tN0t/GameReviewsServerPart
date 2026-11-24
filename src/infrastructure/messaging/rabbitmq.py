import json
from uuid import UUID

import aio_pika

QUEUE_NAME = "rating_recalculation"
DLX_NAME = "rating_recalculation.dlx"
DLQ_NAME = "rating_recalculation.dlq"


async def declare_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractQueue:
    dlx = await channel.declare_exchange(DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx, routing_key=QUEUE_NAME)

    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_NAME,
            "x-dead-letter-routing-key": QUEUE_NAME,
        },
    )
    return queue


class RabbitMQEventBus:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await declare_topology(self._channel)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()

    async def publish_review_changed(self, game_id: UUID) -> None:
        if self._channel is None:
            await self.connect()
        assert self._channel is not None
        body = json.dumps({"game_id": str(game_id)}).encode("utf-8")
        message = aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        await self._channel.default_exchange.publish(message, routing_key=QUEUE_NAME)
