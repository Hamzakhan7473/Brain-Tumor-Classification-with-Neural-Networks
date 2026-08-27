"""
Geometric regional WMH volume zoning (research / Stage-1 MVP).

Without a registered ventricle/brainstem atlas, we approximate:
  - infratentorial: inferior fraction of the brain bounding box (SI axis 0)
  - periventricular: remaining (supratentorial) lesion voxels near the in-plane brain center
  - deep_subcortical: remaining supratentorial lesion voxels

Not equivalent to STRIVE-2 visual grading or atlas-based regionalization.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

METHOD_ID = "geometric_heuristic_v1"
INFRATENTORIAL_SI_FRACTION = 0.28
PERIVENTRICULAR_RADIUS_FRAC = 0.42


def _brain_bbox(flair: np.ndarray) -> Tuple[slice, slice, slice]:
    """Tight bbox of tissue-like voxels (intensity above 10th percentile of positive)."""
    f = np.asarray(flair, dtype=np.float32)
    pos = f[f > 0]
    if pos.size == 0:
        d, h, w = f.shape
        return slice(0, d), slice(0, h), slice(0, w)
    thr = float(np.percentile(pos, 10))
    mask = f > thr
    if not mask.any():
        d, h, w = f.shape
        return slice(0, d), slice(0, h), slice(0, w)
    coords = np.argwhere(mask)
    z0, y0, x0 = coords.min(axis=0)
    z1, y1, x1 = coords.max(axis=0) + 1
    return slice(int(z0), int(z1)), slice(int(y0), int(y1)), slice(int(x0), int(x1))


def regional_wmh_volumes_cc(
    lesion_mask: np.ndarray,
    *,
    voxel_vol_mm3: float,
    flair_volume: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Split a binary 3D lesion mask into regional volumes (cc).

    Parameters
    ----------
    lesion_mask :
        Boolean or 0/1 array shaped (D, H, W).
    voxel_vol_mm3 :
        Voxel volume in mm³.
    flair_volume :
        Optional FLAIR intensity volume (same shape) for brain bbox; if omitted,
        bbox is derived from the lesion mask (or full volume if empty).
    """
    mask = np.asarray(lesion_mask).astype(bool)
    if mask.ndim != 3:
        raise ValueError(f"lesion_mask must be 3D, got shape {mask.shape}")

    vv = float(voxel_vol_mm3) if voxel_vol_mm3 and voxel_vol_mm3 > 0 else 1.0

    if flair_volume is not None and np.asarray(flair_volume).shape == mask.shape:
        zsl, ysl, xsl = _brain_bbox(np.asarray(flair_volume))
    elif mask.any():
        coords = np.argwhere(mask)
        z0, y0, x0 = coords.min(axis=0)
        z1, y1, x1 = coords.max(axis=0) + 1
        # Expand slightly so empty-brain edge cases still get a usable center
        zsl, ysl, xsl = slice(int(z0), int(z1)), slice(int(y0), int(y1)), slice(int(x0), int(x1))
    else:
        d, h, w = mask.shape
        zsl, ysl, xsl = slice(0, d), slice(0, h), slice(0, w)

    z0, z1 = zsl.start, zsl.stop
    y0, y1 = ysl.start, ysl.stop
    x0, x1 = xsl.start, xsl.stop
    si_extent = max(1, z1 - z0)
    infra_cut = z0 + max(1, int(round(si_extent * INFRATENTORIAL_SI_FRACTION)))

    cy = 0.5 * (y0 + y1 - 1)
    cx = 0.5 * (x0 + x1 - 1)
    half_diag = 0.5 * float(np.hypot(max(1, y1 - y0), max(1, x1 - x0)))
    pv_radius = max(1.0, PERIVENTRICULAR_RADIUS_FRAC * half_diag)

    zz, yy, xx = np.indices(mask.shape)
    dist_hw = np.sqrt((yy.astype(np.float64) - cy) ** 2 + (xx.astype(np.float64) - cx) ** 2)
    infra = mask & (zz < infra_cut)
    supra = mask & ~infra
    peri = supra & (dist_hw <= pv_radius)
    deep = supra & ~peri

    def _cc(m: np.ndarray) -> float:
        return round(float(m.sum()) * vv / 1000.0, 4)

    total = _cc(mask)
    peri_cc = _cc(peri)
    deep_cc = _cc(deep)
    infra_cc = _cc(infra)
    # Guard floating drift so regions sum to total
    assigned = round(peri_cc + deep_cc + infra_cc, 4)
    if total > 0 and abs(assigned - total) > 0.01:
        # Prefer adjusting deep (largest residual bucket)
        deep_cc = round(max(0.0, total - peri_cc - infra_cc), 4)

    return {
        "method": METHOD_ID,
        "volume_cc_total": total,
        "volume_cc_periventricular": peri_cc,
        "volume_cc_deep_subcortical": deep_cc,
        "volume_cc_infratentorial": infra_cc,
        "lesion_voxels_periventricular": int(peri.sum()),
        "lesion_voxels_deep_subcortical": int(deep.sum()),
        "lesion_voxels_infratentorial": int(infra.sum()),
        "fraction_periventricular": round(peri_cc / total, 4) if total > 0 else 0.0,
        "fraction_deep_subcortical": round(deep_cc / total, 4) if total > 0 else 0.0,
        "fraction_infratentorial": round(infra_cc / total, 4) if total > 0 else 0.0,
        "note": (
            "Regional volumes use geometric heuristic (inferior SI fraction = infratentorial; "
            "central in-plane radius = periventricular; remainder = deep/subcortical). "
            "Not atlas-registered; research/prototype use only."
        ),
    }
