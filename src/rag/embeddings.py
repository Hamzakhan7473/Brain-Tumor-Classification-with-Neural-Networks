from __future__ import annotations

import os
from typing import List


def embed_text(text: str) -> List[float]:
    """
    Create an embedding vector for the input text using Google embeddings via
    `google-generativeai`.
    """
    text = (text or "").strip()
    if not text:
        return []

    import google.generativeai as genai

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_APIKEY") or ""
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for RAG embeddings.")

    genai.configure(api_key=api_key)

    # Default to a commonly-used embedding model. Can be overridden via env.
    model_id = os.environ.get("RAG_EMBED_MODEL") or "models/text-embedding-004"

    # `embed_content` is the simplest stable API surface in the current library.
    # We use retrieval_document task_type for semantic search.
    result = genai.embed_content(
        model=model_id,
        content=text,
        task_type="retrieval_document",
    )

    # The library may return either a dict-like response or an object.
    if isinstance(result, dict):
        vec = result.get("embedding") or result.get("values")
    else:
        vec = getattr(result, "embedding", None) or getattr(result, "values", None)

    if not vec:
        raise RuntimeError("Failed to extract embedding vector from LLM response.")

    return list(vec)

