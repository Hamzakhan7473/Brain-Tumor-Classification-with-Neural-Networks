"""Compare preprocessed tensor statistics against expected training norms."""

from __future__ import annotations

from typing import Any


def detect_distribution_shift(
    preprocessed_volume: Any,
    expected_stats: dict,
) -> dict:
    """
    Simple mean-offset check vs stored training-validation statistics.
    Returns flags and human-readable warnings (not a calibrated OOD classifier).
    """
    import numpy as np

    vol = np.asarray(preprocessed_volume, dtype=np.float64)
    actual_mean = float(vol.mean())
    actual_std = float(vol.std())

    expected_mean = float(expected_stats.get("mean", 0.0))
    expected_std_val = float(expected_stats.get("std", 1.0))
    expected_mean_std = float(expected_stats.get("mean_std", 0.35))

    mean_z = abs(actual_mean - expected_mean) / max(expected_mean_std, 1e-3)

    is_ood = mean_z > 3.0
    warnings = []

    std_diff = abs(actual_std - expected_std_val)
    std_z = std_diff / max(expected_stats.get("std_std", expected_std_val * 0.35 + 0.08), 1e-6)
    combo = max(mean_z, 0.5 * std_z)

    if combo > 2.0:
        warnings.append(
            "Image/statistics noticeably different from offline validation norms for this checkpoint. "
            "Model calibration may shift; corroborate with independent reading."
        )
    if combo > 2.75:
        is_ood = True

    return {
        "is_ood": is_ood,
        "distribution_z_score": round(mean_z, 3),
        "preproc_mean": round(actual_mean, 5),
        "preproc_std": round(actual_std, 5),
        "warnings": warnings,
    }

