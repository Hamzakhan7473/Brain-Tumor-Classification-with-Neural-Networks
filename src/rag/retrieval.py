from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.rag.embeddings import embed_text
from src.rag.vector_store import search_rag


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    score: Optional[float] = None


async def retrieve_evidence(query_text: str, top_k: int = 5) -> List[EvidenceChunk]:
    """
    Embed `query_text` and query MongoDB Atlas Vector Search for top-k chunks.
    """
    query_embedding = embed_text(query_text)
    if not query_embedding:
        return []

    results = await search_rag(query_embedding=query_embedding, top_k=top_k)
    evidence: List[EvidenceChunk] = []
    for r in results:
        chunk_id = str(r.get("_id") or r.get("chunk_id") or "")
        if not chunk_id:
            continue
        evidence.append(
            EvidenceChunk(
                chunk_id=chunk_id,
                text=str(r.get("text") or ""),
                metadata=dict(r.get("metadata") or {}),
                score=r.get("score") if isinstance(r.get("score"), (int, float)) else None,
            )
        )
    return evidence

