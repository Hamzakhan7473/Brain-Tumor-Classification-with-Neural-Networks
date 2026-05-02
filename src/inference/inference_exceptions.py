"""Inference-layer failures mapped to HTTP 422 by the API."""

from __future__ import annotations

from typing import Any, Optional


class InputValidationFailed(Exception):
    """Uploaded file incompatible with requested model (safe rejection)."""

    def __init__(self, detail: dict):
        self.detail = detail
        super().__init__(detail.get("error", "input_validation_failed"))


class ClinicalContextRequired(Exception):
    """Missing mandatory clinical metadata (e.g. age for 3D risk stratification)."""

    def __init__(self, message: str, extra: Optional[dict[str, Any]] = None):
        self.detail = {"error": "clinical_context_required", "message": message, **(extra or {})}
        super().__init__(message)

