"""Core MCNP research pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .mcnp_input.generator import generate_mcnp_inputs
from .mcnp_output.tally_extractor import extract_tally_csvs
from .mcnp_run.mpi_runner import run_mpi_batch
from .spectra.plotter import plot_spectra


def _skipped_step(reason: str) -> dict[str, Any]:
    return {"ok": True, "skipped": True, "reason": reason, "warnings": [reason], "errors": []}


def _collect_messages(result: dict[str, Any], step_result: dict[str, Any]) -> None:
    result["warnings"].extend(step_result.get("warnings", []))
    result["errors"].extend(step_result.get("errors", []))


def _existing_csv_files_from_output_dir(output_dir: str) -> list[str]:
    output_path = Path(output_dir)
    if not output_path.exists() or not output_path.is_dir():
        return []
    return [str(path) for path in sorted(output_path.glob("*_Data.csv")) if path.is_file()]


def _csv_files_for_plot(config: dict[str, Any], extract_result: dict[str, Any], dry_run: bool) -> list[str]:
    if not extract_result.get("ok"):
        return []

    if dry_run:
        existing_csv_files = _existing_csv_files_from_output_dir(str(config.get("output_dir", "")))
        if existing_csv_files:
            return existing_csv_files
        return [str(item["csv_path"]) for item in extract_result.get("planned_files", []) if item.get("csv_path")]

    return [path for path in extract_result.get("csv_files", []) if Path(path).exists()]


def _planned_extract_from_mpi(config: dict[str, Any], run_mpi_result: dict[str, Any]) -> dict[str, Any]:
    planned_files = []
    for item in run_mpi_result.get("planned", []):
        txt_path = Path(str(item["output_path"]))
        planned_files.append(
            {
                "txt_path": str(txt_path),
                "csv_path": str(txt_path.with_name(txt_path.stem + "_Data.csv")),
                "row_count": None,
                "rows": [],
            }
        )

    return {
        "ok": bool(planned_files),
        "dry_run": True,
        "planned_from_mpi": True,
        "target_dir": str(config.get("output_dir", "")),
        "output_suffix": "_Data.csv",
        "count": len(planned_files),
        "csv_files": [],
        "planned_files": planned_files,
        "processed_files": [],
        "warnings": [],
        "errors": [],
    }


def _planned_plot_from_csvs(csv_files: list[str], output_path: str) -> dict[str, Any]:
    return {
        "ok": bool(csv_files),
        "mode": "merged",
        "dry_run": True,
        "planned_from_pipeline": True,
        "csv_files": csv_files,
        "output_path": str(Path(output_path)),
        "written_files": [],
        "spectra": [],
        "actions": ["planned_plot_linear_and_log"],
        "warnings": [],
        "errors": [],
    }


def _required(config: dict[str, Any], key: str) -> Any:
    if key not in config:
        raise KeyError(f"Missing required config key: {key}")
    return config[key]


def run_core_pipeline(
    config: dict,
    dry_run: bool = True,
    confirm_mpi: bool = False,
) -> dict[str, Any]:
    """Run the core pipeline: inputs -> MPI -> CSV extraction -> plotting."""
    result: dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "steps": {},
        "warnings": [],
        "errors": [],
    }

    try:
        generate_result = generate_mcnp_inputs(
            base_file=str(_required(config, "base_file")),
            output_dir=str(_required(config, "output_dir")),
            distance_cm=float(_required(config, "distance_cm")),
            reference_point=str(_required(config, "reference_point")),
            nps=str(_required(config, "nps")),
            energies=config.get("energies"),
            composite_sources=config.get("composite_sources"),
            custom_energy=config.get("custom_energy"),
            geb_enabled=bool(config.get("geb_enabled", False)),
            geb_params=config.get("geb_params"),
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - exposed as structured pipeline error.
        generate_result = {"ok": False, "warnings": [], "errors": [str(exc)]}

    result["steps"]["generate_inputs"] = generate_result
    _collect_messages(result, generate_result)

    if not generate_result.get("ok"):
        reason = "Skipped because generate_inputs failed"
        result["steps"]["run_mpi"] = _skipped_step(reason)
        result["steps"]["extract_csv"] = _skipped_step(reason)
        result["steps"]["plot_spectra"] = _skipped_step(reason)
        result["warnings"].extend([reason, reason, reason])
        return result

    run_mpi_result = run_mpi_batch(
        target_dir=str(_required(config, "output_dir")),
        mpi_command=str(_required(config, "mpi_command")),
        dry_run=dry_run,
        confirm=confirm_mpi,
        planned_input_files=generate_result.get("planned_files", []) if dry_run else None,
    )
    result["steps"]["run_mpi"] = run_mpi_result
    _collect_messages(result, run_mpi_result)

    if not run_mpi_result.get("ok"):
        reason = "Skipped because run_mpi failed or produced no runnable plan"
        result["steps"]["extract_csv"] = _skipped_step(reason)
        result["steps"]["plot_spectra"] = _skipped_step(reason)
        result["warnings"].extend([reason, reason])
        return result

    extract_result: dict[str, Any] | None = None
    if dry_run and Path(str(_required(config, "output_dir"))).exists():
        candidate_extract_result = extract_tally_csvs(
            target_dir=str(_required(config, "output_dir")),
            dry_run=True,
        )
        if candidate_extract_result.get("ok"):
            extract_result = candidate_extract_result

    if extract_result is None:
        if dry_run and run_mpi_result.get("planned"):
            extract_result = _planned_extract_from_mpi(config, run_mpi_result)
        else:
            extract_result = extract_tally_csvs(
                target_dir=str(_required(config, "output_dir")),
                dry_run=dry_run,
            )

    result["steps"]["extract_csv"] = extract_result
    _collect_messages(result, extract_result)

    if not extract_result.get("ok"):
        reason = "Skipped because extract_csv failed or found no tally data"
        result["steps"]["plot_spectra"] = _skipped_step(reason)
        result["warnings"].append(reason)
        return result

    csv_files = _csv_files_for_plot(config, extract_result, dry_run)
    if not csv_files:
        reason = "Skipped plot_spectra because no CSV files exist"
        result["steps"]["plot_spectra"] = _skipped_step(reason)
        result["warnings"].append(reason)
        result["ok"] = True
        return result

    if dry_run and not all(Path(path).exists() for path in csv_files):
        plot_result = _planned_plot_from_csvs(csv_files, str(_required(config, "plot_output")))
    else:
        plot_result = plot_spectra(
            csv_files=csv_files,
            output_path=str(_required(config, "plot_output")),
            dry_run=dry_run,
        )
    result["steps"]["plot_spectra"] = plot_result
    _collect_messages(result, plot_result)

    result["ok"] = all(step.get("ok") for step in result["steps"].values()) and not result["errors"]
    return result
