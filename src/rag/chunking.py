from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    metadata: dict


def chunk_text(
    text: str,
    *,
    chunk_size_chars: int = 1200,
    overlap_chars: int = 180,
) -> List[str]:
    """
    Simple character-based chunker with overlap.
    Works well for markdown/text knowledge sources and keeps implementation minimal.
    """
    normalized = (text or "").strip()
    if not normalized:
        return []

    if chunk_size_chars <= overlap_chars:
        overlap_chars = max(0, chunk_size_chars // 6)

    chunks: List[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = end - overlap_chars
    return chunks

