"""PageIndex (vectorless) client for clinical doc retrieval — primary engine for Docs Assistant."""

from __future__ import annotations

import json
import os
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOC_TREES_DIR = Path(os.environ.get("NEUROSIGHT_DOC_TREES_DIR", str(_PROJECT_ROOT / "data" / "doc_trees")))
PAGEINDEX_API_KEY = (os.environ.get("PAGEINDEX_API_KEY") or "").strip()


class DocsIndexer:
    """Manages PageIndex tree generation + caching for clinical PDFs."""

    def __init__(self) -> None:
        if not PAGEINDEX_API_KEY:
            raise RuntimeError(
                "PAGEINDEX_API_KEY not set. Get one at https://dash.pageindex.ai"
            )
        from pageindex import PageIndexClient

        self.client = PageIndexClient(api_key=PAGEINDEX_API_KEY)

    def index_document(self, doc_path: Path) -> dict:
        """Ingest a PDF and return metadata + tree. Cached by file hash."""
        doc_path = doc_path.resolve()
        file_bytes = doc_path.read_bytes()
        file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

        DOC_TREES_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = DOC_TREES_DIR / f"{doc_path.stem}_{file_hash}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        result_submit = self.client.submit_document(str(doc_path))
        doc_id = result_submit.get("doc_id")
        if not doc_id:
            raise RuntimeError(f"PageIndex submit_document returned no doc_id: {result_submit}")

        self._wait_document_processing(doc_id)
        tree_payload = self._wait_tree_result(doc_id)
        tree: Any = tree_payload
        if isinstance(tree_payload, dict) and "nodes" in tree_payload:
            tree = tree_payload.get("nodes")

        meta = self.client.get_document(doc_id)
        page_count = int(meta.get("pageNum") or meta.get("page_count") or 0)

        result = {
            "doc_id": doc_id,
            "doc_name": doc_path.name,
            "doc_hash": file_hash,
            "tree": tree,
            "page_count": page_count,
            "section_count": self._count_sections(tree),
        }
        cache_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result

    def _wait_document_processing(self, doc_id: str, timeout_s: float = 900.0, interval_s: float = 3.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            meta = self.client.get_document(doc_id)
            st = (meta.get("status") or "").lower()
            if st == "completed":
                return
            if st == "failed":
                raise RuntimeError(f"PageIndex document processing failed for {doc_id}")
            time.sleep(interval_s)
        raise TimeoutError(f"Timed out waiting for PageIndex document {doc_id}")

    def _wait_tree_result(self, doc_id: str, timeout_s: float = 900.0, interval_s: float = 3.0) -> Any:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            tr = self.client.get_tree(doc_id)
            st = (tr.get("status") or "").lower()
            if st == "completed":
                return tr.get("result", tr)
            if st == "failed":
                raise RuntimeError(f"PageIndex tree generation failed for {doc_id}")
            time.sleep(interval_s)
        raise TimeoutError(f"Timed out waiting for PageIndex tree {doc_id}")

    def _count_sections(self, tree: Any) -> int:
        n = 0

        def walk(x: Any) -> None:
            nonlocal n
            if isinstance(x, dict):
                n += 1
                for ch in x.get("nodes") or x.get("children") or []:
                    walk(ch)
            elif isinstance(x, list):
                for ch in x:
                    walk(ch)

        walk(tree)
        return max(n, 1)

    def query(self, question: str, doc_ids: List[str], max_nodes: int = 8) -> dict:
        """Reasoning-style retrieval via PageIndex Chat API (multi-doc)."""
        t0 = time.perf_counter()
        guard = (
            f"Use at most {max_nodes} distinct sections. Answer with inline numeric citations [1], [2] "
            f"that refer ONLY to retrieved sources. If nothing in the documents answers the question, respond "
            f"exactly with: No relevant source found in knowledge base."
        )
        messages = [{"role": "user", "content": f"{guard}\n\nQuestion:\n{question}"}]
        resp = self.client.chat_completions(
            messages=messages,
            doc_id=doc_ids,
            enable_citations=True,
        )
        if not isinstance(resp, dict):
            raise RuntimeError("Unexpected PageIndex chat response type")

        answer, citations, trace, tokens_used = _parse_chat_completion(resp, doc_ids)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if (
            not citations
            and "no relevant source found in knowledge base" not in (answer or "").lower()
        ):
            answer = "No relevant source found in knowledge base."

        conf = _estimate_confidence(citations)
        return {
            "answer": answer or "No relevant source found in knowledge base.",
            "citations": citations,
            "reasoning_trace": trace or ["PageIndex chat completion (citations enabled)"],
            "confidence": conf,
            "latency_ms": latency_ms,
            "tokens_used": int(tokens_used),
        }


def _estimate_confidence(citations: List[dict]) -> str:
    if not citations:
        return "low"
    scores = [float(c.get("relevance") or 0) for c in citations]
    top = max(scores) if scores else 0.0
    if top >= 0.85:
        return "high"
    if top >= 0.70:
        return "med"
    return "low"


def _parse_chat_completion(
    resp: Dict[str, Any],
    doc_ids: List[str],
) -> Tuple[str, List[dict], List[str], int]:
    choices = resp.get("choices") or []
    msg = (choices[0].get("message") if choices else None) or {}
    content = (msg.get("content") or "").strip()
    tokens_used = 0
    usage = resp.get("usage") or {}
    if isinstance(usage, dict):
        tokens_used = int(usage.get("total_tokens") or usage.get("total_token_count") or 0)

    raw_citations: List[Any] = []
    for key in ("citations", "annotations", "references"):
        v = msg.get(key)
        if isinstance(v, list):
            raw_citations.extend(v)
    if not raw_citations:
        top = resp.get("citations")
        if isinstance(top, list):
            raw_citations.extend(top)

    citations: List[dict] = []
    for rc in raw_citations:
        if isinstance(rc, str):
            continue
        if not isinstance(rc, dict):
            continue
        doc_id = str(
            rc.get("doc_id")
            or rc.get("document_id")
            or (doc_ids[0] if doc_ids else "")
            or rc.get("id")
            or ""
        )
        doc_name = str(rc.get("doc_name") or rc.get("file_name") or rc.get("name") or rc.get("filename") or "")
        section = str(rc.get("section") or rc.get("section_title") or rc.get("title") or "")
        page = rc.get("page", rc.get("page_index", rc.get("pageNum", "—")))
        if isinstance(page, float):
            page = int(page)
        node_id = str(rc.get("node_id") or rc.get("id") or "")
        snippet = str(rc.get("snippet") or rc.get("excerpt") or rc.get("text") or rc.get("quote") or "")
        if len(snippet) > 280:
            snippet = snippet[:280]
        rel = rc.get("relevance_score", rc.get("score", rc.get("relevance", 0.82)))
        try:
            relevance = float(rel)
        except (TypeError, ValueError):
            relevance = 0.82
        citations.append(
            {
                "doc_id": doc_id,
                "doc_name": doc_name or "document",
                "section": section or "—",
                "page": page if page is not None else "—",
                "node_id": node_id,
                "snippet": snippet,
                "relevance": min(max(relevance, 0.0), 1.0),
            }
        )

    trace: List[str] = []
    rs = msg.get("reasoning") or msg.get("reasoning_content")
    if isinstance(rs, str) and rs.strip():
        trace.append(rs.strip())
    elif isinstance(rs, list):
        trace.extend(str(x) for x in rs if str(x).strip())

    return content, citations, trace, tokens_used


_indexer: Optional[DocsIndexer] = None


def get_indexer() -> DocsIndexer:
    global _indexer
    if _indexer is None:
        _indexer = DocsIndexer()
    return _indexer
