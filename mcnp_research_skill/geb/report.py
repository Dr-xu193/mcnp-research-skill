"""GEB report generation."""

from __future__ import annotations

from typing import Any

from .model import evaluate_geb


def _params_tuple(params: dict | None) -> tuple[float | None, float | None, float | None]:
    if not params:
        return None, None, None
    return (
        params.get("A", params.get("a")),
        params.get("B", params.get("b")),
        params.get("C", params.get("c")),
    )


def build_geb_report(analysis_result: dict) -> dict[str, Any]:
    """Build a structured text report from a GEB CSV analysis result."""
    warnings = list(analysis_result.get("warnings", []))
    errors = list(analysis_result.get("errors", []))
    fitted = analysis_result.get("fitted_params")
    reference = analysis_result.get("reference_params", {})
    detected_points = analysis_result.get("detected_points", [])

    lines: list[str] = []
    lines.append("GEB CSV Analysis Report")
    lines.append("=" * 80)

    if not fitted:
        lines.append("No fitted GEB parameters are available.")
        for warning in warnings:
            lines.append(f"WARNING: {warning}")
        for error in errors:
            lines.append(f"ERROR: {error}")
        return {
            "ok": False,
            "report_text": "\n".join(lines),
            "warnings": warnings,
            "errors": errors,
        }

    ref_A, ref_B, ref_C = _params_tuple(reference)
    labels = ["A", "B", "C"]
    ref_values = [ref_A, ref_B, ref_C]
    fit_values = [fitted["A"], fitted["B"], fitted["C"]]

    lines.append("Parameter | Reference | Fitted | Difference")
    lines.append("-" * 80)
    for label, ref_val, fit_val in zip(labels, ref_values, fit_values):
        if ref_val is None:
            diff_text = "n/a"
            ref_text = "n/a"
        else:
            diff_text = f"{fit_val - float(ref_val):+.6f}"
            ref_text = f"{float(ref_val):.6f}"
        lines.append(f"{label:<9} | {ref_text:<9} | {fit_val:.6f} | {diff_text}")

    lines.append("")
    lines.append("Detected Peak | Actual FWHM | Fitted FWHM | Error")
    lines.append("-" * 80)
    for point in detected_points:
        energy = float(point["energy"])
        fwhm = float(point["fwhm"])
        calc = evaluate_geb(energy, fitted["A"], fitted["B"], fitted["C"])["value"]
        error_pct = abs(calc - fwhm) / fwhm * 100 if fwhm != 0 else 0.0
        lines.append(f"{energy:<13.4f} | {fwhm:<11.5f} | {calc:<11.5f} | {error_pct:.2f}%")

    return {
        "ok": True,
        "report_text": "\n".join(lines),
        "warnings": warnings,
        "errors": errors,
    }

