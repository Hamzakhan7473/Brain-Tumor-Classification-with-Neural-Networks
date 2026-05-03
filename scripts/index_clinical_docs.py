#!/usr/bin/env python3
"""
Index clinical documents for PageIndex (PDF, or Markdown converted to PDF).

Run during CI/CD or after updating docs/:
  PAGEINDEX_API_KEY=... python scripts/index_clinical_docs.py

PageIndex accepts PDF only; .md files are rendered to simple PDFs under
data/doc_trees/_staging/ (ASCII-safe lines; unicode replaced with spaces).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Optional explicit list (PDF preferred). Missing paths are skipped with a warning.
CLINICAL_DOCS: list[str] = [
    "docs/validation-protocol-v1.pdf",
    "docs/regulatory-roadmap.pdf",
    "docs/intended-use-statement.pdf",
    "docs/compliance-baseline.pdf",
    "docs/safety-escalation-sop.pdf",
    "docs/clinical-workflow.pdf",
    "docs/radiologist-signoff-protocol.pdf",
    "docs/references/fazekas-1987-ajnr.pdf",
    "docs/references/wardlaw-2013-strive.pdf",
    "docs/references/kuijf-2019-wmh-challenge.pdf",
    "docs/references/fda-saMD-guidance.pdf",
]


def _md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    from fpdf import FPDF

    text = md_path.read_text(encoding="utf-8", errors="replace")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for line in text.splitlines():
        safe = "".join(ch if 32 <= ord(ch) < 127 or ch in "\t" else " " for ch in line)
        chunk = safe if len(safe) <= 2400 else safe[:2397] + "..."
        try:
            pdf.multi_cell(0, 4.5, chunk)
        except Exception:
            pdf.multi_cell(0, 4.5, chunk.encode("ascii", "replace").decode("ascii"))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))


def _resolve_paths() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for rel in CLINICAL_DOCS:
        p = (_ROOT / rel).resolve()
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists():
            out.append(p)
        else:
            try:
                disp = p.relative_to(_ROOT)
            except ValueError:
                disp = p
            print(f"⚠ Missing: {disp}")
    for md in sorted(_ROOT.glob("docs/**/*.md")):
        key = str(md.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(md)
    kb = _ROOT / "src" / "data" / "clinical_kb"
    if kb.is_dir():
        for md in sorted(kb.glob("**/*.md")):
            key = str(md.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(md)
    return out


def main() -> None:
    from src.rag.pageindex_client import DOC_TREES_DIR, get_indexer

    indexer = get_indexer()
    staging = DOC_TREES_DIR / "_staging"
    staging.mkdir(parents=True, exist_ok=True)

    indexed: list[dict] = []
    for path in _resolve_paths():
        pdf_path = path
        if path.suffix.lower() != ".pdf":
            h = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:10]
            pdf_path = staging / f"{path.stem}_{h}.pdf"
            try:
                rel = path.relative_to(_ROOT)
            except ValueError:
                rel = path
            print(f"Converting {rel} → {pdf_path.name} …")
            _md_to_pdf(path, pdf_path)
        print(f"Indexing {path.name} …")
        result = indexer.index_document(pdf_path)
        indexed.append(
            {
                "doc_id": result["doc_id"],
                "name": result["doc_name"],
                "sections": result["section_count"],
                "pages": result["page_count"],
            }
        )
        print(f"  ✓ {result['section_count']} sections, {result['page_count']} pages ({result['doc_id']})")

    manifest_path = DOC_TREES_DIR / "manifest.json"
    payload = {
        "documents": indexed,
        "total": len(indexed),
        "indexed": len(indexed) > 0,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n✓ Wrote manifest ({len(indexed)} documents) → {manifest_path.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
