from collections.abc import Sequence
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings


def _normalise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert psycopg3 native types (UUID, datetime) to plain Python scalars.

    psycopg3 returns UUID columns as uuid.UUID and timestamp columns as
    datetime objects.  Downstream code (Pydantic models, json.dumps) expects
    plain strings / ISO strings, so we normalise once at the fetch boundary.
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

pool: AsyncConnectionPool | None = None


async def init_db() -> None:
    global pool
    settings = get_settings()
    if not settings.database_url:
        return

    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": None,
        },
        open=False,
    )
    await pool.open()


async def close_db() -> None:
    if pool:
        await pool.close()


def is_configured() -> bool:
    return pool is not None


async def fetch_one(query: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    if pool is None:
        return None
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            row = await cur.fetchone()
            return _normalise_row(row) if row is not None else None


async def fetch_all(query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    if pool is None:
        return []
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            rows = await cur.fetchall()
            return [_normalise_row(r) for r in rows]


async def execute(query: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    return await fetch_one(query, params)
