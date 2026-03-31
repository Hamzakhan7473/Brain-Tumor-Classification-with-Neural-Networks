"""
RAG ingestion entrypoint.

Intended for GCP Cloud Run Jobs / Cloud Scheduler:
- Reads knowledge sources (default: `docs/**/*.md`)
- Chunks text into fixed-size overlaps
- Creates embeddings using Google embeddings (GOOGLE_API_KEY required)
- Upserts chunks + embeddings into MongoDB Atlas Vector Search collection

Required env vars:
- GOOGLE_API_KEY
- MONGODB_URI
Optional env vars:
- MONGODB_DB
- MONGODB_COLLECTION_RAG
- MONGODB_RAG_VECTOR_INDEX (used later when querying)
- RAG_EMBED_MODEL (default: models/text-embedding-004)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Iterable, List

from src.rag.chunking import chunk_text
from src.rag.embeddings import embed_text
from src.rag.vector_store import upsert_rag_chunks


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def iter_docs(glob: str) -> Iterable[Path]:
    # glob is relative to repo root
    repo_root = Path(__file__).resolve().parents[1]
    return sorted(repo_root.glob(glob))


def build_chunk_docs(*, source_path: Path, chunks: List[str], doc_id_prefix: str) -> List[Dict]:
    built: List[Dict] = []
    for idx, ch in enumerate(chunks):
        chunk_id = _sha256(f"{doc_id_prefix}:{idx}:{source_path.as_posix()}")
        built.append(
            {
                "chunk_id": chunk_id,
                "text": ch,
                "metadata": {
                    "source_path": source_path.as_posix(),
                    "chunk_index": idx,
                    "doc_id": doc_id_prefix,
                },
            }
        )
    return built


async def ingest(
    *,
    docs_glob: str,
    chunk_size_chars: int,
    overlap_chars: int,
    batch_size: int,
    max_docs: int | None,
) -> None:
    docs = list(iter_docs(docs_glob))
    if max_docs is not None:
        docs = docs[:max_docs]

    if not docs:
        print("No documents found for glob:", docs_glob)
        return

    print(f"Found {len(docs)} docs for ingestion.")

    pending: List[Dict] = []
    for doc_idx, path in enumerate(docs, start=1):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(raw, chunk_size_chars=chunk_size_chars, overlap_chars=overlap_chars)
        if not chunks:
            continue

        doc_id_prefix = _sha256(path.as_posix())
        chunk_docs = build_chunk_docs(
            source_path=path,
            chunks=chunks,
            doc_id_prefix=doc_id_prefix,
        )

        for cd in chunk_docs:
            embedding = embed_text(cd["text"])
            cd["embedding"] = embedding
            pending.append(cd)

            if len(pending) >= batch_size:
                await upsert_rag_chunks(pending)
                pending = []

        print(f"[{doc_idx}/{len(docs)}] Ingested doc: {path.as_posix()} (chunks={len(chunks)})")

    if pending:
        await upsert_rag_chunks(pending)
    print("Ingestion completed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-glob", default="docs/**/*.md", help="Glob for knowledge docs (repo-root relative)")
    parser.add_argument("--chunk-size-chars", type=int, default=1200)
    parser.add_argument("--overlap-chars", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-docs", type=int, default=None)
    args = parser.parse_args()

    asyncio.run(
        ingest(
            docs_glob=args.docs_glob,
            chunk_size_chars=args.chunk_size_chars,
            overlap_chars=args.overlap_chars,
            batch_size=args.batch_size,
            max_docs=args.max_docs,
        )
    )


if __name__ == "__main__":
    main()

