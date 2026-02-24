"""
Redis / ARQ pool for enqueueing case-processing jobs.

UM-API only enqueues jobs (run_j1_pdf_extraction to tier1_queue).
UM-Jobs workers consume from Redis. Pool is created at startup and closed at shutdown.
"""

import logging
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

logger = logging.getLogger(__name__)

_arq_pool: Optional[ArqRedis] = None

# Queue and function names must match UM-Jobs worker registration
TIER1_QUEUE = "tier1_queue"
JOB_START_CASE = "run_j1_pdf_extraction"


async def get_arq_pool() -> ArqRedis:
    """Return the global ARQ Redis pool. Raises if not initialized."""
    global _arq_pool
    if _arq_pool is None:
        raise RuntimeError("ARQ pool not initialized. Call init_arq_pool() at startup.")
    return _arq_pool


async def init_arq_pool() -> None:
    """Create the ARQ pool. Call once during app lifespan startup."""
    global _arq_pool
    if _arq_pool is not None:
        return
    try:
        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
        _arq_pool = await create_pool(redis_settings)
        logger.info("ARQ pool connected to Redis (queue=%s)", TIER1_QUEUE)
    except Exception as e:
        logger.warning("ARQ pool init failed (case processing will use in-process fallback): %s", e)


async def close_arq_pool() -> None:
    """Close the ARQ pool. Call during app lifespan shutdown."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None
        logger.info("ARQ pool closed")


async def enqueue_case_processing(case_id: str, user_id: str) -> Optional[str]:
    """
    Enqueue the first job of the case pipeline (J1). UM-Jobs workers pick it up.
    Returns job_id if enqueued, None if Redis/ARQ unavailable.
    """
    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job(
            JOB_START_CASE,
            case_id=case_id,
            user_id=user_id,
            _queue_name=TIER1_QUEUE,
        )
        return job.job_id if job else None
    except Exception as e:
        logger.warning("Enqueue case processing failed: %s", e)
        return None
