"""Reject pixel arrays / NIfTI / DICOM / heatmap tensors before they reach the LLM."""

from __future__ import annotations

from typing import Any

REJECT_PIXEL_LEAK = "REJECT_PIXEL_LEAK"

_LEAK_KEYS = frozenset(
    {
        "pixels",
        "pixel_array",
        "nifti",
        "nifti_bytes",
        "dicom",
        "dicom_bytes",
        "heatmap",
        "heatmap_tensor",
        "volume",
        "image_bytes",
        "scan_bytes",
        "saliency_map_b64",
        "visual_overlay",
    }
)


class PayloadRejected(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _is_binary_blob(value: Any) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return True
    except Exception:
        pass
    return False


def _looks_like_numeric_volume(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    if len(value) < 16:
        return False
    head = value[:8]
    return all(isinstance(x, (int, float, list)) for x in head)


def find_pixel_leaks(obj: Any, *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if _is_binary_blob(obj) or _looks_like_numeric_volume(obj):
        hits.append(path)
        return hits
    if isinstance(obj, dict):
        for key, val in obj.items():
            key_l = str(key).lower()
            child = f"{path}.{key}"
            if key_l in _LEAK_KEYS and val not in (None, "", [], {}, False):
                if key_l in {"heatmap", "visual_overlay"} and isinstance(val, dict):
                    allowed = set(val.keys()) <= {"present", "bbox_ids"}
                    if allowed:
                        continue
                hits.append(child)
                continue
            hits.extend(find_pixel_leaks(val, path=child))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:32]):
            hits.extend(find_pixel_leaks(item, path=f"{path}[{i}]"))
    return hits


def validate_payload(payload: dict) -> dict:
    """Prompt is built only from schema-valid JSON without pixel arrays."""
    if not isinstance(payload, dict):
        raise PayloadRejected("REJECT_PAYLOAD_SCHEMA", "payload must be an object")
    leaks = find_pixel_leaks(payload)
    if leaks:
        raise PayloadRejected(REJECT_PIXEL_LEAK, ",".join(leaks[:12]))
    return payload


def prompt_has_pixel_leak(prompt: str) -> bool:
    blob = prompt or ""
    return "\x89PNG" in blob or "data:image" in blob.lower()


def heatmap_metadata_only(visual_overlay: Any) -> dict[str, Any] | None:
    """Allow {present, bbox_ids} only. Drop PNG bytes / tensors."""
    if visual_overlay is None:
        return None
    if isinstance(visual_overlay, dict):
        present = bool(visual_overlay.get("present"))
        raw_ids = visual_overlay.get("bbox_ids") or []
        ids = [str(x) for x in (raw_ids if isinstance(raw_ids, list) else [])][:16]
        return {"present": present, "bbox_ids": ids}
    return None
