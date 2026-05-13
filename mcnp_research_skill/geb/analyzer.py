"""GEB CSV analysis orchestration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .constants import M_E_C2, SP2_WEIGHTS
from .efficiency import calculate_net_efficiency
from .features import extract_geb_features
from .fitter import fit_geb_parameters
from .report import build_geb_report


def _normalize_reference_params(reference_params: dict) -> dict[str, float]:
    return {
        "A": float(reference_params.get("A", reference_params.get("a", 0.0))),
        "B": float(reference_params.get("B", reference_params.get("b", 0.0))),
        "C": float(reference_params.get("C", reference_params.get("c", 0.0))),
    }


def _detect_nuclide(file_name: str) -> str | None:
    fn_upper = file_name.upper()
    for key in SP2_WEIGHTS:
        parts = key.split("-")
        if parts[0] in fn_upper and parts[1] in fn_upper:
            return key
    return None


def _sampling_fraction(file_name: str, peak_E: float) -> float:
    detected_nuclide = _detect_nuclide(file_name)
    is_composite = "composite" in file_name.lower()
    sp2_dict = SP2_WEIGHTS.get(detected_nuclide, {}) if (detected_nuclide and is_composite) else {}
    if not sp2_dict:
        return 1.0

    closest_e = min(sp2_dict.keys(), key=lambda energy: abs(energy - peak_E))
    sp2_weight = sp2_dict.get(closest_e, 1.0)
    sp2_total = sum(sp2_dict.values())
    return sp2_weight / sp2_total if sp2_total > 1e-9 else 1.0


def run_geb_csv_analysis(
    csv_jobs: list[dict],
    reference_params: dict,
) -> dict[str, Any]:
    """Run CSV-based GEB peak/FWHM extraction, efficiency integration, and fitting."""
    result: dict[str, Any] = {
        "ok": False,
        "csv_jobs": csv_jobs,
        "reference_params": {},
        "detected_points": [],
        "fitted_params": None,
        "fit_result": None,
        "efficiencies": [],
        "warnings": [],
        "errors": [],
        "report_text": "",
    }

    try:
        normalized_ref = _normalize_reference_params(reference_params)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"Invalid reference_params: {exc}")
        return result
    result["reference_params"] = normalized_ref

    if not csv_jobs:
        result["errors"].append("csv_jobs must not be empty")
        return result

    for job in csv_jobs:
        csv_path = str(job.get("path", ""))
        peak_ranges = job.get("peaks", [])
        file_name = os.path.basename(csv_path)

        if not Path(csv_path).exists():
            result["errors"].append(f"CSV file does not exist: {csv_path}")
            continue

        for idx, peak_range in enumerate(peak_ranges):
            feature = extract_geb_features(csv_path, tuple(peak_range), normalized_ref)
            if not feature.get("ok"):
                result["warnings"].extend(feature.get("warnings", []))
                result["errors"].extend(feature.get("errors", []))
                continue

            peak_E = float(feature["peak_E"])
            fwhm = float(feature["fwhm"])
            result["detected_points"].append(
                {
                    "csv_path": csv_path,
                    "channel": idx + 1,
                    "energy": peak_E,
                    "fwhm": fwhm,
                    "peak_range": tuple(peak_range),
                }
            )

            sampling_fraction = _sampling_fraction(file_name, peak_E)
            efficiency = calculate_net_efficiency(
                feature["energy"],
                feature["counts"],
                peak_E,
                fwhm,
                sampling_fraction=sampling_fraction,
            )
            efficiency.update(
                {
                    "csv_path": csv_path,
                    "channel": idx + 1,
                    "compton_edge": (2 * peak_E**2) / (M_E_C2 + 2 * peak_E),
                }
            )
            result["warnings"].extend(efficiency.get("warnings", []))
            result["errors"].extend(efficiency.get("errors", []))
            result["efficiencies"].append(efficiency)

    pairs = [(point["energy"], point["fwhm"]) for point in result["detected_points"]]
    if len(pairs) < 3:
        result["warnings"].append("Fewer than 3 valid peaks detected; skipping GEB fit")
        report = build_geb_report(result)
        result["report_text"] = report["report_text"]
        return result

    fit_result = fit_geb_parameters(pairs)
    result["fit_result"] = fit_result
    result["warnings"].extend(fit_result.get("warnings", []))
    result["errors"].extend(fit_result.get("errors", []))
    if fit_result.get("ok"):
        result["fitted_params"] = fit_result["fitted_params"]
        result["ok"] = not result["errors"]

    report = build_geb_report(result)
    result["report_text"] = report["report_text"]
    return result

