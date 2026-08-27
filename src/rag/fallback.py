"""MongoDB Atlas vector RAG fallback when PageIndex is unavailable."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional


async def vector_rag_query(
    question: str,
    *,
    top_k: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retrieve chunks via vector search and compose an answer (optional Gemini).
    Returns the same shape as ``DocsIndexer.query`` for API compatibility.
    """
    from src.rag.retrieval import retrieve_evidence

    t0 = time.perf_counter()
    k = int(top_k or os.environ.get("RAG_TOP_K", "5"))
    evidence = await retrieve_evidence(question, top_k=k)

    citations: List[Dict[str, Any]] = []
    evidence_blocks: List[str] = []
    for i, e in enumerate(evidence, start=1):
        text = (e.text or "").strip()
        snippet = text[:280] if len(text) > 280 else text
        meta = e.metadata or {}
        source = str(meta.get("source_path") or meta.get("source") or meta.get("path") or meta.get("doc_id") or "")
        title = str(meta.get("title") or meta.get("heading") or meta.get("section") or "Chunk")
        rel = float(e.score) if isinstance(e.score, (int, float)) else 0.75
        citations.append(
            {
                "doc_id": str(e.chunk_id),
                "doc_name": source or "rag_chunk",
                "section": title,
                "page": "—",
                "node_id": str(e.chunk_id),
                "snippet": snippet,
                "relevance": min(max(rel, 0.0), 1.0),
            }
        )
        block = text if len(text) <= 900 else text[:900] + "…"
        evidence_blocks.append(f"[{i}] (chunk_id: {e.chunk_id})\n{block}")

    evidence_context = "\n\n".join(evidence_blocks).strip()
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if not evidence_context:
        return {
            "answer": "No relevant source found in knowledge base.",
            "citations": [],
            "reasoning_trace": ["MongoDB Atlas vector search returned no chunks."],
            "confidence": "low",
            "latency_ms": latency_ms,
            "tokens_used": 0,
        }

    answer_text = ""
    tokens_used = 0
    try:
        from src.llm.client import get_llm_client

        prompt = (
            "You are a clinical workflow assistant. Answer using ONLY the evidence provided. "
            "Cite sources inline using bracket numbers like [1], [2] matching the evidence order. "
            "If the evidence does not support a claim, say 'insufficient evidence from retrieved sources'. "
            "Keep the answer concise.\n\n"
            f"Question: {question}\n\nEvidence:\n{evidence_context}\n"
        )
        client = get_llm_client()
        resp = client.generate_content(prompt)
        answer_text = ((resp.text if resp else "") or "").strip()
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            tokens_used = int(
                getattr(usage, "total_token_count", 0) or getattr(usage, "total_tokens", 0) or 0
            )
    except Exception:
        answer_text = (
            "Retrieved evidence is listed in citations. Configure BEDROCK_MODEL_ID or "
            "GOOGLE_API_KEY for a narrative answer."
        )

    if not answer_text:
        answer_text = "Insufficient evidence from retrieved sources."

    conf = _estimate_confidence(citations)
    return {
        "answer": answer_text,
        "citations": citations,
        "reasoning_trace": ["MongoDB Atlas vector search + optional LLM synthesis"],
        "confidence": conf,
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
    }


def _estimate_confidence(citations: List[dict]) -> str:
    if not citations:
        return "low"
    top = max(float(c.get("relevance") or 0) for c in citations)
    if top >= 0.85:
        return "high"
    if top >= 0.70:
        return "med"
    return "low"
