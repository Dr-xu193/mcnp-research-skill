"""GEB feature extraction from CSV spectra."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _select_columns(df: pd.DataFrame) -> tuple[str, str]:
    df.columns = df.columns.str.strip()
    x_cols = [c for c in df.columns if "energy" in c.lower() or "mev" in c.lower()]
    y_cols = [c for c in df.columns if "tally" in c.lower() or "count" in c.lower()]
    x_column = x_cols[0] if x_cols else df.columns[0]
    y_column = y_cols[0] if y_cols else df.columns[1]
    return str(x_column), str(y_column)


def extract_geb_features(
    csv_path: str,
    peak_range: tuple[float, float],
    reference_params: dict,
) -> dict[str, Any]:
    """Extract peak energy and FWHM from a CSV spectrum within one ROI."""
    result: dict[str, Any] = {
        "ok": False,
        "csv_path": csv_path,
        "peak_range": tuple(peak_range),
        "reference_params": reference_params,
        "peak_E": None,
        "fwhm": None,
        "energy": [],
        "counts": [],
        "x_column": None,
        "y_column": None,
        "warnings": [],
        "errors": [],
    }

    if not Path(csv_path).exists():
        result["errors"].append(f"CSV file does not exist: {csv_path}")
        return result

    try:
        e_min, e_max = float(peak_range[0]), float(peak_range[1])
        df = pd.read_csv(csv_path)
        if len(df.columns) < 2:
            raise ValueError("CSV must contain at least two columns")
        x_column, y_column = _select_columns(df)
        energy = df[x_column].to_numpy(dtype=float)
        counts = df[y_column].to_numpy(dtype=float)
    except Exception as exc:  # noqa: BLE001 - returned structurally.
        result["errors"].append(str(exc))
        return result

    result["x_column"] = x_column
    result["y_column"] = y_column
    result["energy"] = energy.tolist()
    result["counts"] = counts.tolist()

    mask = (energy > e_min) & (energy < e_max)
    E_roi = energy[mask]
    C_roi = counts[mask]

    if len(E_roi) == 0:
        result["warnings"].append("No data points inside peak range")
        return result

    peak_idx = int(np.argmax(C_roi))
    peak_E = float(E_roi[peak_idx])
    half_max = float(C_roi[peak_idx] / 2.0)

    left_E = None
    right_E = None
    for i in range(peak_idx, 0, -1):
        if C_roi[i - 1] <= half_max <= C_roi[i]:
            left_E = float(
                E_roi[i - 1]
                + (half_max - C_roi[i - 1]) * (E_roi[i] - E_roi[i - 1]) / (C_roi[i] - C_roi[i - 1])
            )
            break

    for i in range(peak_idx, len(C_roi) - 1):
        if C_roi[i + 1] <= half_max <= C_roi[i]:
            right_E = float(
                E_roi[i]
                + (half_max - C_roi[i]) * (E_roi[i + 1] - E_roi[i]) / (C_roi[i + 1] - C_roi[i])
            )
            break

    if left_E is None or right_E is None:
        result["warnings"].append("Could not determine both FWHM crossing points")
        result["peak_E"] = peak_E
        return result

    result["ok"] = True
    result["peak_E"] = peak_E
    result["fwhm"] = float(right_E - left_E)
    return result

