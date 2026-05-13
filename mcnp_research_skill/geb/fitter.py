"""GEB parameter fitting."""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit

from .model import geb_formula_values


def fit_geb_parameters(
    energy_fwhm_pairs: list[tuple[float, float]],
    p0: list[float] | tuple[float, float, float] | None = None,
    bounds: tuple[list[float], list[float]] | tuple[tuple[float, float, float], tuple[float, float, float]] | None = None,
    maxfev: int = 10000,
) -> dict[str, Any]:
    """Fit GEB parameters from ``(energy, fwhm)`` pairs."""
    result: dict[str, Any] = {
        "ok": False,
        "input_count": len(energy_fwhm_pairs),
        "detected_points": energy_fwhm_pairs,
        "fitted_params": None,
        "covariance": None,
        "warnings": [],
        "errors": [],
    }

    if len(energy_fwhm_pairs) < 3:
        result["warnings"].append("At least 3 valid peaks are required to fit A/B/C")
        return result

    try:
        energies = np.asarray([pair[0] for pair in energy_fwhm_pairs], dtype=float)
        fwhm = np.asarray([pair[1] for pair in energy_fwhm_pairs], dtype=float)
        fit_p0 = p0 if p0 is not None else [-0.01, 0.05, 0.2]
        fit_bounds = bounds if bounds is not None else ([-1.0, 0.0, 0.0], [1.0, 5.0, 5.0])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", OptimizeWarning)
            popt, pcov = curve_fit(
                geb_formula_values,
                energies,
                fwhm,
                p0=fit_p0,
                bounds=fit_bounds,
                maxfev=maxfev,
            )
    except Exception as exc:  # noqa: BLE001 - exposed as structured fitting error.
        result["errors"].append(str(exc))
        return result

    for warning in caught:
        result["warnings"].append(str(warning.message))

    result["ok"] = True
    result["fitted_params"] = {
        "A": float(popt[0]),
        "B": float(popt[1]),
        "C": float(popt[2]),
    }
    result["covariance"] = np.asarray(pcov, dtype=float).tolist()
    return result
