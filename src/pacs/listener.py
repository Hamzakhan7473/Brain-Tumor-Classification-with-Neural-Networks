"""
DICOM C-STORE listener scaffold (Phase B+).

Intended sidecar flow:
1. Listen on ``PACS_PORT`` (default 11112) with AE title ``PACS_AE_TITLE``.
2. De-identify incoming instances (strip PHI; keep UIDs only where policy allows).
3. Hash MRN → ``patient.mrn_hash``; never persist raw MRN or patient name.
4. ``POST`` de-identified metadata + object storage pointer to ``/shadow/ingest``.

For pilot deployments without on-prem PACS routing, hospitals can call ``POST /shadow/ingest``
directly (authenticated) instead of running this listener.

Optional dependency: ``pynetdicom`` (not required for API-only pilots).

Example (future):
    pip install pynetdicom
    python -m src.pacs.listener
"""

from __future__ import annotations

import os


def main() -> None:
    """Placeholder entrypoint — implement C-STORE SCP with pynetdicom when infra is ready."""
    ae_title = os.environ.get("PACS_AE_TITLE", "NEUROSIGHT")
    port = int(os.environ.get("PACS_PORT", "11112"))
    raise SystemExit(
        f"PACS listener not started (scaffold only). AE_TITLE={ae_title} PORT={port}. "
        "Install pynetdicom and implement C-STORE → de-id → /shadow/ingest, or use POST /shadow/ingest."
    )


if __name__ == "__main__":
    main()
