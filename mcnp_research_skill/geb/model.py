"""GEB mathematical model."""

from __future__ import annotations

from typing import Any

import numpy as np


def geb_formula_values(E: Any, A: float, B: float, C: float):
    """Return raw GEB FWHM values for scalar or array-like energy input."""
    return A + B * np.sqrt(np.maximum(np.asarray(E, dtype=float) + C * np.asarray(E, dtype=float) ** 2, 0))


def evaluate_geb(E, A: float, B: float, C: float) -> dict[str, Any]:
    """Evaluate ``A + B * sqrt(E + C * E^2)`` and return a structured result."""
    values = geb_formula_values(E, A, B, C)
    if np.isscalar(E):
        value = float(np.asarray(values))
        values_list = [value]
    else:
        values_list = np.asarray(values, dtype=float).tolist()
        value = values_list[0] if len(values_list) == 1 else None

    return {
        "ok": True,
        "input": E,
        "value": value,
        "values": values_list,
        "params": {"A": float(A), "B": float(B), "C": float(C)},
        "warnings": [],
        "errors": [],
    }

