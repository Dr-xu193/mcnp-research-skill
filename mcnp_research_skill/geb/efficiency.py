"""Net-efficiency calculations for GEB CSV analysis."""

from __future__ import annotations

from typing import Any

import numpy as np


def calculate_net_efficiency(
    energy: list[float],
    counts: list[float],
    peak_E: float,
    fwhm: float,
    sampling_fraction: float = 1.0,
) -> dict[str, Any]:
    """Calculate gross area, trapezoid background, and net efficiency."""
    result: dict[str, Any] = {
        "ok": False,
        "peak_E": peak_E,
        "fwhm": fwhm,
        "sampling_fraction": sampling_fraction,
        "gross_area": 0.0,
        "background_area": 0.0,
        "net_raw": 0.0,
        "net_efficiency": 0.0,
        "roi": None,
        "warnings": [],
        "errors": [],
    }

    try:
        E = np.asarray(energy, dtype=float)
        C = np.asarray(counts, dtype=float)
        peak = float(peak_E)
        width = float(fwhm)
        fraction = float(sampling_fraction)
    except (TypeError, ValueError) as exc:
        result["errors"].append(str(exc))
        return result

    if width <= 0:
        result["errors"].append("fwhm must be positive")
        return result

    roi_min = peak - 1.5 * width
    roi_max = peak + 1.5 * width
    mask = (E >= roi_min) & (E <= roi_max)
    roi_counts = C[mask]
    result["roi"] = {"min": roi_min, "max": roi_max, "bin_count": int(len(roi_counts))}

    if len(roi_counts) < 6:
        result["ok"] = True
        result["warnings"].append("Fewer than 6 ROI bins; returning zero areas as in legacy logic")
        return result

    gross_area = float(np.sum(roi_counts))
    left_baseline = float(np.mean(roi_counts[:3]))
    right_baseline = float(np.mean(roi_counts[-3:]))
    num_bins = int(len(roi_counts))
    background_area = float((left_baseline + right_baseline) * num_bins / 2.0)
    net_raw = gross_area - background_area
    net_efficiency = net_raw / fraction if fraction > 1e-9 else net_raw

    result.update(
        {
            "ok": True,
            "gross_area": gross_area,
            "background_area": background_area,
            "net_raw": float(net_raw),
            "net_efficiency": float(net_efficiency),
        }
    )
    return result

