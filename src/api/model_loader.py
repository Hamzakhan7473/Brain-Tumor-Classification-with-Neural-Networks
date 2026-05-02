"""
Thin adapter: FastAPI warmup delegates to TensorFlow/Keras ``ModelRegistry``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_registry():
    """Return the singleton Keras inference registry (src.inference.model_registry)."""
    from src.inference.model_registry import registry

    return registry


class _CompatLoader:
    """Mimics the old registry API surface for main.py remnants."""

    def warm(self, project_root: Path) -> None:
        from src.inference.model_registry import registry

        try:
            registry.load_all()
        except Exception as e:
            logger.exception("Inference registry warmup failed: %s", e)
            raise

    def get(self, name: str) -> Optional[Any]:
        return get_registry().get_model(name)

    def names(self):
        return sorted(get_registry().models.keys())


_registry = None


def get_compat_registry():
    """Legacy singleton used by gradual refactors."""
    global _registry
    if _registry is None:
        _registry = _CompatLoader()
    return _registry
