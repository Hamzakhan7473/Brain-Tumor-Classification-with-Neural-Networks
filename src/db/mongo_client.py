from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.db.settings import load_mongo_settings


@lru_cache(maxsize=1)
def get_motor_client() -> Any | None:
    """
    Create (and cache) a single Motor client for the app process.

    Returns `None` when Mongo is not configured.
    """
    settings = load_mongo_settings()
    if not settings.enable:
        return None

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError as e:
        raise RuntimeError(
            "MongoDB enabled but `motor` dependency is missing. "
            "Add `motor` to requirements and reinstall."
        ) from e

    return AsyncIOMotorClient(settings.uri)


def get_motor_database():
    client = get_motor_client()
    if client is None:
        return None
    return client[load_mongo_settings().db_name]

