from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from src.db.mongo_client import get_motor_database
from src.db.settings import load_mongo_settings


def _vector_index_name() -> str:
    return os.environ.get("MONGODB_RAG_VECTOR_INDEX", "rag_vector_index")


async def upsert_rag_chunks(chunks: Iterable[Dict[str, Any]]) -> None:
    """
    Insert/update RAG chunks into MongoDB.

    Expected chunk schema:
    {
      chunk_id: str,
      text: str,
      metadata: {...},
      embedding: List[float]
    }
    """
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return

    coll = db[settings.rag_collection]
    # Upsert by chunk_id (stored as _id for efficient upserts).
    ops = []
    for ch in chunks:
        chunk_id = ch.get("chunk_id")
        if not chunk_id:
            continue
        doc = dict(ch)
        doc["_id"] = chunk_id
        ops.append(
            {
                "updateOne": {
                    "filter": {"_id": chunk_id},
                    "update": {"$set": doc},
                    "upsert": True,
                }
            }
        )

    if not ops:
        return

    await coll.bulk_write(ops)


async def search_rag(
    *,
    query_embedding: List[float],
    top_k: int = 5,
    index_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve top-k evidence chunks using MongoDB Atlas Vector Search.
    Requires a vector index configured on:
      - collection: `settings.rag_collection`
      - embedding field: `embedding`
    """
    db = get_motor_database()
    settings = load_mongo_settings()
    if db is None or not settings.enable:
        return []
    if not query_embedding:
        return []

    coll = db[settings.rag_collection]
    idx = index_name or _vector_index_name()

    pipeline = [
        {
            "$vectorSearch": {
                "index": idx,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": max(50, top_k * 10),
                "limit": top_k,
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]

    cursor = coll.aggregate(pipeline)
    results: List[Dict[str, Any]] = []
    async for doc in cursor:
        results.append(doc)
    return results

