import sys
from enum import Enum

from config import IS_PYTEST_RUN, REDIS_URL
from logger.logger import log
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from rq import Queue


class QueuePrio(Enum):
    HIGH = "high"
    DEFAULT = "default"
    LOW = "low"


redis_client = Redis.from_url(str(REDIS_URL), decode_responses=True)

high_prio_queue = Queue(name=QueuePrio.HIGH.value, connection=redis_client)
default_queue = Queue(name=QueuePrio.DEFAULT.value, connection=redis_client)
low_prio_queue = Queue(name=QueuePrio.LOW.value, connection=redis_client)


def __get_sync_cache() -> Redis:
    if IS_PYTEST_RUN:
        # Only import fakeredis when running tests, as it is a test dependency.
        from fakeredis import FakeRedis

        return FakeRedis(version=7)

    log.info(f"Connecting to sync redis in {sys.argv[0]}...")
    # A separate client that auto-decodes responses is needed
    client = Redis.from_url(str(REDIS_URL), decode_responses=True)
    log.info(f"Redis sync connection established in {sys.argv[0]}!")
    return client


def __get_async_cache() -> AsyncRedis:
    if IS_PYTEST_RUN:
        # Only import fakeredis when running tests, as it is a test dependency.
        from fakeredis import FakeAsyncRedis

        return FakeAsyncRedis(version=7)

    log.info(f"Connecting to async redis in {sys.argv[0]}...")
    # A separate client that auto-decodes responses is needed
    client = AsyncRedis.from_url(str(REDIS_URL), decode_responses=True)
    log.info(f"Redis async connection established in {sys.argv[0]}!")
    return client


sync_cache = __get_sync_cache()
async_cache = __get_async_cache()
