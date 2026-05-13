"""SPE parsing and GEB parameter inference."""

from __future__ import annotations

import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import NUCLIDE_ENERGIES, SPE_CALIBRATIONS
from .fitter import fit_geb_parameters


def parse_spe_file(path: str) -> dict[str, Any]:
    """Parse a SPE file and return measurement date plus spectrum counts."""
    result: dict[str, Any] = {
        "ok": False,
        "path": path,
        "measurement_date": None,
        "spectrum": [],
        "warnings": [],
        "errors": [],
    }
    spe_path = Path(path)
    if not spe_path.exists():
        result["errors"].append(f"SPE file does not exist: {path}")
        return result

    try:
        lines = spe_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for index, raw_line in enumerate(lines):
            line = raw_line.strip()
            if line == "$DATE_MEA:":
                try:
                    measurement_date = datetime.strptime(lines[index + 1].strip(), "%m/%d/%Y %H:%M:%S")
                    result["measurement_date"] = measurement_date.isoformat()
                except Exception as exc:  # noqa: BLE001
                    result["warnings"].append(f"Failed to parse $DATE_MEA: {exc}")
            elif line == "$DATA:":
                start, end = map(int, lines[index + 1].split())
                count = end - start + 1
                result["spectrum"] = [int(value.strip()) for value in lines[index + 2 : index + 2 + count]]
                break
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"Failed to read SPE file: {exc}")
        return result

    if not result["spectrum"]:
        result["errors"].append("No $DATA spectrum found in SPE file")
        return result

    result["ok"] = True
    return result


def identify_nuclide_from_filename(filename: str) -> dict[str, Any]:
    """Identify supported calibration nuclide from a SPE filename."""
    fn_upper = os.path.basename(filename).upper()
    for key, energies in NUCLIDE_ENERGIES.items():
        parts = key.split("-")
        if parts[0] in fn_upper and parts[1] in fn_upper:
            return {
                "ok": True,
                "filename": filename,
                "nuclide": key,
                "energies": energies,
                "warnings": [],
                "errors": [],
            }
    return {
        "ok": False,
        "filename": filename,
        "nuclide": None,
        "energies": [],
        "warnings": [f"Unable to identify nuclide from filename: {filename}"],
        "errors": [],
    }


def select_spe_calibration(filename: str, measurement_date: str | None = None) -> dict[str, Any]:
    """Select the 4-29 or 4-30 SPE energy calibration."""
    fn_upper = os.path.basename(filename).upper()
    calibration_key = "4-29"
    if measurement_date:
        try:
            parsed = datetime.fromisoformat(measurement_date)
            if parsed.day == 30:
                calibration_key = "4-30"
        except ValueError:
            pass
    if "4-30" in fn_upper or "4.30" in fn_upper:
        calibration_key = "4-30"
    elif "4-29" in fn_upper or "4.29" in fn_upper:
        calibration_key = "4-29"

    return {
        "ok": True,
        "filename": filename,
        "measurement_date": measurement_date,
        "calibration_key": calibration_key,
        "calibration": SPE_CALIBRATIONS[calibration_key],
        "warnings": [],
        "errors": [],
    }


def _theoretical_channel(e_mev: float, calibration: dict[str, float], spectrum_length: int) -> int:
    e_kev = e_mev * 1000.0
    a, b, c = calibration["a"], calibration["b"], calibration["c"]
    if c == 0:
        center_ch = int((e_kev - a) / b) if b != 0 else 512
    else:
        delta = b**2 - 4 * c * (a - e_kev)
        center_ch = int((-b + math.sqrt(delta)) / (2 * c)) if delta > 0 else 512
    return max(0, min(spectrum_length - 1, center_ch))


def _extract_one_energy_fwhm(
    spectrum: list[int],
    e_mev: float,
    calibration: dict[str, float],
) -> dict[str, Any]:
    center_ch = _theoretical_channel(e_mev, calibration, len(spectrum))
    left_search = max(0, center_ch - 15)
    right_search = min(len(spectrum) - 1, center_ch + 15)
    peak_slice = spectrum[left_search : right_search + 1]
    if not peak_slice:
        return {"ok": False, "warnings": ["Empty peak search slice"], "errors": []}

    real_center_ch = left_search + peak_slice.index(max(peak_slice))
    max_counts = spectrum[real_center_ch]
    half_max = max_counts / 2.0

    left_fwhm_ch = real_center_ch
    while left_fwhm_ch > 0 and spectrum[left_fwhm_ch] > half_max:
        left_fwhm_ch -= 1

    right_fwhm_ch = real_center_ch
    while right_fwhm_ch < len(spectrum) - 1 and spectrum[right_fwhm_ch] > half_max:
        right_fwhm_ch += 1

    fwhm_channels = right_fwhm_ch - left_fwhm_ch
    dE_dCh = calibration["b"] + 2 * calibration["c"] * real_center_ch
    fwhm_mev = (fwhm_channels * dE_dCh) / 1000.0

    if not (0.001 < fwhm_mev < 0.2):
        return {
            "ok": False,
            "energy_mev": e_mev,
            "fwhm_mev": fwhm_mev,
            "warnings": [f"Rejected abnormal FWHM for {e_mev:.3f} MeV: {fwhm_mev:.5f}"],
            "errors": [],
        }

    return {
        "ok": True,
        "energy_mev": e_mev,
        "fwhm_mev": float(fwhm_mev),
        "center_channel": center_ch,
        "real_center_channel": real_center_ch,
        "fwhm_channels": fwhm_channels,
        "warnings": [],
        "errors": [],
    }


def extract_fwhm_points_from_spe(
    spe_files: list[str],
) -> dict[str, Any]:
    """Extract valid ``energy_mev``/``fwhm_mev`` points from SPE files."""
    result: dict[str, Any] = {
        "ok": False,
        "energy_fwhm_pairs": [],
        "used_files": [],
        "skipped_files": [],
        "warnings": [],
        "errors": [],
    }

    for path in spe_files:
        filename = os.path.basename(path)
        identification = identify_nuclide_from_filename(filename)
        if not identification["ok"]:
            result["skipped_files"].append({"path": path, "reason": "unidentified_nuclide"})
            result["warnings"].extend(identification["warnings"])
            continue

        parsed = parse_spe_file(path)
        if not parsed["ok"]:
            result["errors"].extend(parsed["errors"])
            result["warnings"].extend(parsed["warnings"])
            continue

        calibration = select_spe_calibration(filename, parsed.get("measurement_date"))
        file_points = []
        for e_mev in identification["energies"]:
            point = _extract_one_energy_fwhm(parsed["spectrum"], e_mev, calibration["calibration"])
            if point["ok"]:
                point["path"] = path
                point["nuclide"] = identification["nuclide"]
                point["calibration_key"] = calibration["calibration_key"]
                file_points.append(point)
                result["energy_fwhm_pairs"].append(
                    {"energy_mev": point["energy_mev"], "fwhm_mev": point["fwhm_mev"], "path": path}
                )
            else:
                result["warnings"].extend(point.get("warnings", []))
                result["errors"].extend(point.get("errors", []))

        if file_points:
            result["used_files"].append({"path": path, "points": file_points})
        else:
            result["skipped_files"].append({"path": path, "reason": "no_valid_fwhm_points"})

    result["ok"] = len(result["energy_fwhm_pairs"]) > 0 and not result["errors"]
    return result


def fit_geb_from_spe_files(
    spe_files: list[str],
) -> dict[str, Any]:
    """Infer GEB parameters from one or more SPE files."""
    extracted = extract_fwhm_points_from_spe(spe_files)
    result: dict[str, Any] = {
        **extracted,
        "fitted_params": None,
        "fit_result": None,
    }

    pairs = [(item["energy_mev"], item["fwhm_mev"]) for item in result["energy_fwhm_pairs"]]
    if len(pairs) < 3:
        result["ok"] = False
        result["warnings"].append("At least 3 valid SPE peaks are required to fit GEB parameters")
        return result

    fit_result = fit_geb_parameters(
        pairs,
        bounds=([-1.0, 0.0, -1.0], [1.0, 1.0, 10.0]),
    )
    result["fit_result"] = fit_result
    result["warnings"].extend(fit_result.get("warnings", []))
    result["errors"].extend(fit_result.get("errors", []))
    if fit_result.get("ok"):
        result["ok"] = True
        result["fitted_params"] = fit_result["fitted_params"]
    else:
        result["ok"] = False
    return result
