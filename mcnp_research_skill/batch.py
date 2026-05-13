"""Batch orchestration for reproducible MCNP research runs."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from .manifest import build_manifest, write_manifest
from .pipeline import run_core_pipeline


def expand_distance_range(start_cm: float, end_cm: float, step_cm: float) -> list[float]:
    """Expand an inclusive distance range using decimal arithmetic."""
    start = Decimal(str(start_cm))
    end = Decimal(str(end_cm))
    step = Decimal(str(step_cm))
    if step <= 0:
        raise ValueError("distance_step must be greater than 0")
    if end < start:
        raise ValueError("distance_end must be greater than or equal to distance_start")

    values: list[float] = []
    current = start
    while current <= end:
        values.append(float(current))
        current += step
    return values


def kev_to_mev(energy_kev: float) -> float:
    """Convert keV to MeV with stable decimal-style rounding."""
    return round(float(energy_kev) / 1000.0, 9)


def _distance_label(distance_cm: float) -> str:
    return f"{distance_cm:g}"


def _subrun_config(config: dict[str, Any], distance_cm: float) -> dict[str, Any]:
    output_root = Path(str(config["output_dir"]))
    subdir = output_root / f"distance_{_distance_label(distance_cm)}cm"
    custom_energy = config.get("custom_energy")
    if custom_energy is None and config.get("custom_energy_kev") is not None:
        custom_energy = kev_to_mev(float(config["custom_energy_kev"]))

    return {
        "base_file": str(config["base_file"]),
        "output_dir": str(subdir),
        "distance_cm": distance_cm,
        "reference_point": str(config["reference_point"]),
        "nps": str(config["nps"]),
        "energies": config.get("energies", [] if custom_energy is not None else None),
        "composite_sources": config.get("composite_sources", []),
        "custom_energy": custom_energy,
        "geb_enabled": bool(config.get("geb_enabled", False)),
        "geb_params": config.get("geb_params"),
        "mpi_command": str(config["mpi_command"]),
        "plot_output": str(subdir / "spectra.png"),
    }


def _base_result(config: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": dry_run,
        "output_dir": str(config.get("output_dir", "")),
        "distances_cm": [],
        "subruns": [],
        "manifest_preview": None,
        "manifest_path": None,
        "warnings": [],
        "errors": [],
    }


def run_batch_pipeline(
    config: dict[str, Any],
    dry_run: bool = True,
    confirm_mpi: bool = False,
) -> dict[str, Any]:
    """Run or plan a distance-expanded MCNP pipeline batch."""
    result = _base_result(config, dry_run)

    if not dry_run and not confirm_mpi:
        result["errors"].append("confirm_mpi=True is required when dry_run=False")
        return result

    try:
        distances = expand_distance_range(
            float(config["distance_start"]),
            float(config["distance_end"]),
            float(config["distance_step"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        result["errors"].append(str(exc))
        return result

    result["distances_cm"] = distances

    subruns: list[dict[str, Any]] = []
    for distance in distances:
        sub_config = _subrun_config(config, distance)
        pipeline_result = run_core_pipeline(sub_config, dry_run=dry_run, confirm_mpi=confirm_mpi)
        subrun = {
            "distance_cm": distance,
            "output_dir": sub_config["output_dir"],
            "config": sub_config,
            "result": pipeline_result,
        }
        subruns.append(subrun)
        result["warnings"].extend(pipeline_result.get("warnings", []))
        result["errors"].extend(pipeline_result.get("errors", []))

    result["subruns"] = subruns
    result["ok"] = bool(subruns) and all(item["result"].get("ok") for item in subruns) and not result["errors"]

    manifest = build_manifest(
        config=config,
        dry_run=dry_run,
        subruns=subruns,
        warnings=result["warnings"],
        errors=result["errors"],
    )
    if dry_run:
        result["manifest_preview"] = manifest
        return result

    manifest_path = Path(str(config["output_dir"])) / "manifest.json"
    write_result = write_manifest(manifest, manifest_path)
    result["manifest_path"] = str(manifest_path)
    if not write_result["ok"]:
        result["ok"] = False
        result["errors"].extend(write_result["errors"])
    return result
