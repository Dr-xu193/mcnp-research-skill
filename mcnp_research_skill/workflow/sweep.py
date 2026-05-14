"""Point-source distance sweep preparation.

Generates multiple prepared MCNP decks from a single input by varying
the source position along an axis.  Only ``point_sdef_pos`` is supported.
Does **not** run MCNP, extract CSV, or plot.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from ..mcnp_run.mpi_runner import run_mpi_batch
from .postprocess import postprocess_workflow
from .prepare import prepare_workflow

VALID_AXES = {"x", "y", "z"}


def _expand_distances(
    distances: list[float] | None,
    start: float | None,
    stop: float | None,
    step: float | None,
) -> tuple[list[float] | None, list[str]]:
    """Return (distances, errors)."""
    if distances is not None:
        try:
            return [float(d) for d in distances], []
        except (TypeError, ValueError):
            return None, [{"code": "INVALID_DISTANCES", "message": f"Invalid distances: {distances!r}"}]
    if start is None or stop is None or step is None:
        return None, []
    if step <= 0:
        return None, [{"code": "INVALID_SWEEP_RANGE", "message": "sweep step must be > 0"}]
    if start > stop:
        return None, [{"code": "INVALID_SWEEP_RANGE", "message": "sweep start must be <= stop"}]
    values: list[float] = []
    curr = float(start)
    end = float(stop)
    s = float(step)
    while curr <= end + 1e-9:
        values.append(round(curr, 9))
        curr += s
    return values, []


def _compute_position(
    reference: list[float],
    axis: str,
    direction: float,
    distance: float,
) -> list[float]:
    idx = {"x": 0, "y": 1, "z": 2}[axis]
    pos = list(reference)
    pos[idx] = reference[idx] + direction * distance
    return pos


def _distance_label(d: float) -> str:
    if d == int(d):
        return f"d{int(d)}"
    return f"d{d}"


def prepare_point_sweep(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    distances: list[float] | None = None,
    start: float | None = None,
    stop: float | None = None,
    step: float | None = None,
    axis: str = "z",
    reference_position: tuple[float, float, float] | list[float] = (0, 0, 0),
    direction: int | float = 1,
    source_energy: float | str,
    source_particle: str | int | None = None,
    nps: str | int | float | None = None,
    postprocess: str = "none",
) -> dict[str, Any]:
    """Generate a distance sweep of point-source prepared decks."""

    in_path = Path(input_path)
    wd = Path(work_dir)
    errors: list[str] = []
    warnings: list[str] = []

    # ---- validate ----
    if axis not in VALID_AXES:
        errors.append({"code": "INVALID_SWEEP_AXIS", "message": f"Invalid axis '{axis}'; must be one of {sorted(VALID_AXES)}"})

    try:
        ref_pos = [float(v) for v in reference_position]
        if len(ref_pos) != 3:
            errors.append({"code": "INVALID_REFERENCE_POSITION", "message": f"reference_position must have exactly 3 values, got {len(ref_pos)}"})
    except (TypeError, ValueError):
        errors.append({"code": "INVALID_REFERENCE_POSITION", "message": f"Invalid reference_position: {reference_position!r}"})

    try:
        energy = float(source_energy)
        if energy <= 0:
            errors.append({"code": "MISSING_SOURCE_ENERGY", "message": f"source_energy must be positive, got {energy}"})
    except (TypeError, ValueError):
        errors.append({"code": "MISSING_SOURCE_ENERGY", "message": f"Invalid source_energy: {source_energy!r}"})

    dir_val = float(direction)

    dists, dist_errs = _expand_distances(distances, start, stop, step)
    if dist_errs:
        errors.extend(dist_errs)
    if dists is None:
        errors.append({"code": "INVALID_SWEEP_RANGE", "message": "No distances specified; provide either --distances or --start/--stop/--step"})

    if errors:
        return {"ok": False, "schema_version": "1.0", "input_path": str(in_path),
                "work_dir": str(wd), "errors": errors, "warnings": []}

    if not in_path.exists():
        return {"ok": False, "schema_version": "1.0", "input_path": str(in_path),
                "work_dir": str(wd), "errors": [{"code": "INPUT_FILE_NOT_FOUND", "message": f"Input file does not exist: {input_path}"}], "warnings": []}

    # ---- process each distance ----
    wd.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    prepared = 0
    failed = 0

    for d in dists:
        pos = _compute_position(ref_pos, axis, dir_val, d)
        label = _distance_label(d)
        subdir = wd / label
        prep = prepare_workflow(
            input_path=in_path,
            work_dir=subdir,
            workflow_mode="patch-and-run",
            source_strategy="point_sdef_pos",
            source_position=pos,
            source_energy=energy,
            source_particle=source_particle,
            nps=nps,
            postprocess=postprocess,
        )
        item_errors = prep.get("errors", [])
        # Normalise string errors to structured dicts
        normalised: list[dict] = []
        for e in item_errors:
            if isinstance(e, dict):
                normalised.append(e)
            else:
                normalised.append({"code": "PREPARE_FAILED", "message": str(e)})
        entry = {
            "distance": d,
            "source_position": [float(v) for v in pos],
            "work_dir": str(subdir),
            "prepared_input_path": prep.get("prepared_input_path"),
            "ok": prep.get("ok", False),
            "blocked": prep.get("blocked", []),
            "errors": normalised,
            "warnings": prep.get("warnings", []),
        }
        items.append(entry)
        if entry["ok"]:
            prepared += 1
        else:
            failed += 1
        warnings.extend(entry.get("warnings", []))

    all_ok = failed == 0

    result: dict[str, Any] = {
        "ok": all_ok or prepared > 0,
        "schema_version": "1.0",
        "input_path": str(in_path),
        "work_dir": str(wd),
        "source_strategy": "point_sdef_pos",
        "axis": axis,
        "reference_position": [float(v) for v in ref_pos],
        "direction": dir_val,
        "distances": dists,
        "prepared_count": prepared,
        "failed_count": failed,
        "items": items,
        "artifacts": {},
        "warnings": warnings,
        "errors": [],
    }

    if not all_ok and prepared == 0:
        result["ok"] = False
        result["errors"].append({"code": "SWEEP_ALL_FAILED", "message": "All distance points failed to prepare"})

    # ---- write sweep manifest ----
    manifest_path = wd / "sweep_manifest.json"
    try:
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["artifacts"]["sweep_manifest_json"] = str(manifest_path)
    except OSError:
        pass

    return result


def run_point_sweep(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    distances: list[float] | None = None,
    start: float | None = None,
    stop: float | None = None,
    step: float | None = None,
    axis: str = "z",
    reference_position: tuple[float, float, float] | list[float] = (0, 0, 0),
    direction: int | float = 1,
    source_energy: float | str,
    source_particle: str | int | None = None,
    nps: str | int | float | None = None,
    postprocess: str = "none",
    mpi_config_path: str | Path | None = None,
    execute: bool = False,
    confirm_mpi: bool = False,
    mcnp_outputs: list[str] | None = None,
    csv_dir: str | Path | None = None,
    plot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare sweep → optionally run → optionally postprocess."""

    wd = Path(work_dir)
    in_path = Path(input_path)

    # ---- prepare sweep ----
    prep = prepare_point_sweep(
        input_path=in_path, work_dir=wd,
        distances=distances, start=start, stop=stop, step=step,
        axis=axis, reference_position=reference_position, direction=direction,
        source_energy=source_energy, source_particle=source_particle,
        nps=nps, postprocess=postprocess,
    )

    result: dict[str, Any] = {
        "ok": False, "schema_version": "1.0",
        "dry_run": not execute, "executed": False,
        "prepared_count": prep.get("prepared_count", 0),
        "runner_input_files": [],
        "run": {"status": "not_started"},
        "postprocess_status": "not_requested" if postprocess == "none" else "planned_not_executed",
        "artifacts": prep.get("artifacts", {}),
        "errors": prep.get("errors", []),
        "warnings": prep.get("warnings", []),
    }

    if not prep.get("ok"):
        return result

    items = prep.get("items", [])
    ok_items = [i for i in items if i["ok"]]

    if not ok_items:
        return result

    # ---- build runner file list ----
    input_name = in_path.name
    stem = os.path.splitext(input_name)[0]
    runner_files: list[str] = []
    for item in ok_items:
        d = item["distance"]
        label = _distance_label(d)
        name = f"{label}_{input_name}"
        runner_files.append(name)
    result["runner_input_files"] = runner_files

    # ---- dry-run ----
    if not execute:
        result["ok"] = True
        result["run"]["status"] = "skipped_dry_run"
        result["run"]["reason"] = "Pass --execute --confirm-mpi to run MCNP."
        return result

    # ---- safety gates ----
    if not confirm_mpi:
        result["ok"] = False; result["dry_run"] = False
        result["errors"].append({"code": "MISSING_CONFIRM_MPI", "message": "Refusing to run MCNP without --confirm-mpi."})
        return result
    if mpi_config_path is None:
        result["ok"] = False; result["dry_run"] = False
        result["errors"].append({"code": "MISSING_MPI_CONFIG", "message": "MCNP execution requires --mpi-config."})
        return result

    # ---- stage runner inputs ----
    staging = wd / "runner_inputs"
    staging.mkdir(parents=True, exist_ok=True)
    for item, name in zip(ok_items, runner_files):
        src = Path(item["prepared_input_path"])
        shutil.copy2(src, staging / name)
    result["runner_inputs_dir"] = str(staging)

    # ---- load MPI config ----
    try:
        cfg_text = Path(mpi_config_path).read_text(encoding="utf-8")
        try:
            import yaml
            mpi_cfg = yaml.safe_load(cfg_text)
        except ImportError:
            mpi_cfg = {}
    except OSError as exc:
        result["ok"] = False; result["dry_run"] = False
        result["errors"].append({"code": "MPI_CONFIG_LOAD_FAILED", "message": str(exc)})
        return result
    mpi_command = str(mpi_cfg.get("mpi_command", "")) if isinstance(mpi_cfg, dict) else ""

    # ---- call runner ----
    try:
        runner_result = run_mpi_batch(
            target_dir=str(staging), mpi_command=mpi_command,
            dry_run=False, confirm=True, input_files=runner_files,
        )
    except Exception as exc:
        result["ok"] = False; result["dry_run"] = False
        result["run"]["status"] = "failed"
        result["errors"].append({"code": "RUNNER_FAILED", "message": str(exc)})
        return result

    if not runner_result.get("ok"):
        result["ok"] = False; result["dry_run"] = False
        result["run"]["status"] = "failed"
        result["errors"].extend(
            {"code": "RUNNER_ERROR", "message": str(e)}
            for e in runner_result.get("errors", [])
        )
        return result

    result["ok"] = True; result["dry_run"] = False; result["executed"] = True
    result["run"]["status"] = "completed"
    result["run"]["runner_summary"] = {
        k: runner_result.get(k) for k in ("commands", "completed", "failed") if k in runner_result
    }

    # ---- postprocess ----
    if postprocess == "none":
        _write_sweep_manifest(wd, result, "run_sweep_manifest.json")
        return result

    csv_base = Path(csv_dir) if csv_dir else wd / "postprocess_csv"
    plot_base = Path(plot_dir) if plot_dir else wd / "postprocess_plots"
    csv_base.mkdir(parents=True, exist_ok=True)
    plot_base.mkdir(parents=True, exist_ok=True)
    completed_runner = runner_result.get("completed", [])
    pp_ok = 0; pp_fail = 0

    for i, (item, name) in enumerate(zip(ok_items, runner_files)):
        mcnp_out = None
        if mcnp_outputs and i < len(mcnp_outputs):
            mcnp_out = mcnp_outputs[i]
        elif i < len(completed_runner):
            mcnp_out = completed_runner[i].get("output_path")
        stem_item = os.path.splitext(name)[0]
        pp = postprocess_workflow(
            input_path=Path(item["prepared_input_path"]),
            work_dir=item["work_dir"], mode=postprocess,
            mcnp_output_path=mcnp_out,
            csv_output_path=csv_base / f"{stem_item}.csv",
            plot_output_path=plot_base / f"{stem_item}.png",
        )
        item["postprocess"] = {"ok": pp.get("ok"), "artifacts": pp.get("artifacts", {}),
                               "blocked": pp.get("blocked", []), "errors": pp.get("errors", [])}
        if pp.get("ok"):
            pp_ok += 1
        else:
            pp_fail += 1

    result["postprocess_summary"] = {"succeeded": pp_ok, "failed": pp_fail}
    if pp_fail > 0 and pp_ok > 0:
        result["warnings"].append(f"Postprocess: {pp_ok} succeeded, {pp_fail} failed")
    elif pp_fail > 0 and pp_ok == 0:
        result["ok"] = False
        result["errors"].append({"code": "POSTPROCESS_ALL_FAILED", "message": "Postprocess failed for all files"})

    _write_sweep_manifest(wd, result, "run_sweep_manifest.json")
    return result


def prepare_disk_sweep(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    distances: list[float] | None = None,
    start: float | None = None,
    stop: float | None = None,
    step: float | None = None,
    axis: str = "z",
    reference_position: tuple[float, float, float] | list[float] = (0, 0, 0),
    direction: int | float = 1,
    source_energy: float | str,
    source_radius: float | str,
    source_particle: str | int | None = None,
    source_ext: float | str = 0,
    source_card_id: int | str | None = None,
    nps: str | int | float | None = None,
    postprocess: str = "none",
) -> dict[str, Any]:
    """Generate a distance sweep of disk_tr1 prepared decks."""

    errors: list[dict] = []
    wd = Path(work_dir)
    in_path = Path(input_path)

    # axis / reference / direction validation
    if axis not in VALID_AXES:
        errors.append({"code": "INVALID_SWEEP_AXIS", "message": f"Invalid axis '{axis}'"})
    try:
        ref_pos = [float(v) for v in reference_position]
        if len(ref_pos) != 3:
            errors.append({"code": "INVALID_REFERENCE_POSITION", "message": f"Must have 3 values, got {len(ref_pos)}"})
    except (TypeError, ValueError):
        errors.append({"code": "INVALID_REFERENCE_POSITION", "message": str(reference_position)})

    try:
        energy = float(source_energy)
        if energy <= 0:
            errors.append({"code": "MISSING_SOURCE_ENERGY", "message": "source_energy must be positive"})
    except (TypeError, ValueError):
        errors.append({"code": "MISSING_SOURCE_ENERGY", "message": str(source_energy)})

    try:
        rad = float(source_radius)
        if rad <= 0:
            errors.append({"code": "MISSING_SOURCE_RADIUS", "message": "source_radius must be positive"})
    except (TypeError, ValueError):
        errors.append({"code": "MISSING_SOURCE_RADIUS", "message": str(source_radius)})

    dir_val = float(direction)
    dists, dist_errs = _expand_distances(distances, start, stop, step)
    if dist_errs:
        errors.extend(dist_errs)
    if dists is None:
        errors.append({"code": "INVALID_SWEEP_RANGE", "message": "No distances specified"})
    if errors:
        return {"ok": False, "schema_version": "1.0", "input_path": str(in_path), "work_dir": str(wd),
                "errors": errors, "warnings": []}

    if not in_path.exists():
        return {"ok": False, "schema_version": "1.0", "input_path": str(in_path), "work_dir": str(wd),
                "errors": [{"code": "INPUT_FILE_NOT_FOUND", "message": f"File does not exist: {input_path}"}], "warnings": []}

    wd.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []; prepared = 0; failed = 0; warnings: list[str] = []

    for d in dists:
        pos = _compute_position(ref_pos, axis, dir_val, d)
        label = _distance_label(d)
        subdir = wd / label
        prep = prepare_workflow(
            input_path=in_path, work_dir=subdir,
            workflow_mode="patch-and-run", source_strategy="disk_tr1",
            source_position=pos, source_energy=energy, source_radius=rad,
            source_particle=source_particle, source_ext=source_ext, source_card_id=source_card_id,
            nps=nps, postprocess=postprocess,
        )
        item_errors = prep.get("errors", [])
        normalised = [e if isinstance(e, dict) else {"code": "PREPARE_FAILED", "message": str(e)} for e in item_errors]
        entry = {"distance": d, "source_position": [float(v) for v in pos], "work_dir": str(subdir),
                 "prepared_input_path": prep.get("prepared_input_path"), "ok": prep.get("ok", False),
                 "blocked": prep.get("blocked", []), "errors": normalised, "warnings": prep.get("warnings", [])}
        items.append(entry)
        if entry["ok"]: prepared += 1
        else: failed += 1
        warnings.extend(entry.get("warnings", []))

    all_ok = failed == 0
    result: dict[str, Any] = {"ok": all_ok or prepared > 0, "schema_version": "1.0", "input_path": str(in_path),
        "work_dir": str(wd), "source_strategy": "disk_tr1",
        "axis": axis, "reference_position": [float(v) for v in ref_pos], "direction": dir_val,
        "distances": dists, "prepared_count": prepared, "failed_count": failed,
        "items": items, "artifacts": {}, "warnings": warnings, "errors": []}
    if not all_ok and prepared == 0:
        result["ok"] = False; result["errors"].append({"code": "SWEEP_ALL_FAILED", "message": "All distance points failed"})
    manifest_path = wd / "disk_sweep_manifest.json"
    try:
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["artifacts"]["disk_sweep_manifest_json"] = str(manifest_path)
    except OSError:
        pass
    return result


def run_disk_sweep(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    distances: list[float] | None = None,
    start: float | None = None,
    stop: float | None = None,
    step: float | None = None,
    axis: str = "z",
    reference_position: tuple[float, float, float] | list[float] = (0, 0, 0),
    direction: int | float = 1,
    source_energy: float | str,
    source_radius: float | str,
    source_particle: str | int | None = None,
    source_ext: float | str = 0,
    source_card_id: int | str | None = None,
    nps: str | int | float | None = None,
    postprocess: str = "none",
    mpi_config_path: str | Path | None = None,
    execute: bool = False,
    confirm_mpi: bool = False,
    mcnp_outputs: list[str] | None = None,
    csv_dir: str | Path | None = None,
    plot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare disk sweep → optionally run → optionally F8 postprocess."""

    wd = Path(work_dir); in_path = Path(input_path)

    prep = prepare_disk_sweep(
        input_path=in_path, work_dir=wd,
        distances=distances, start=start, stop=stop, step=step,
        axis=axis, reference_position=reference_position, direction=direction,
        source_energy=source_energy, source_radius=source_radius,
        source_particle=source_particle, source_ext=source_ext, source_card_id=source_card_id,
        nps=nps, postprocess=postprocess,
    )

    result: dict[str, Any] = {
        "ok": False, "schema_version": "1.0", "dry_run": not execute, "executed": False,
        "prepared_count": prep.get("prepared_count", 0), "runner_input_files": [],
        "run": {"status": "not_started"},
        "postprocess_status": "not_requested" if postprocess == "none" else "planned_not_executed",
        "artifacts": prep.get("artifacts", {}), "errors": prep.get("errors", []), "warnings": prep.get("warnings", []),
    }

    if not prep.get("ok"):
        return result

    items = prep.get("items", []); ok_items = [i for i in items if i["ok"]]
    result["items"] = items
    if not ok_items:
        return result

    input_name = in_path.name; stem = os.path.splitext(input_name)[0]
    raw_files = [f"d{i['distance']}_{input_name}" for i in ok_items]
    runner_files = [f.replace(".0_", "_") if ".0_" in f else f for f in raw_files]
    result["runner_input_files"] = runner_files

    if not execute:
        result["ok"] = True; result["run"]["status"] = "skipped_dry_run"
        return result
    if not confirm_mpi:
        result["ok"] = False; result["dry_run"] = False
        result["errors"].append({"code": "MISSING_CONFIRM_MPI", "message": "Refusing to run MCNP without --confirm-mpi."})
        return result
    if mpi_config_path is None:
        result["ok"] = False; result["dry_run"] = False
        result["errors"].append({"code": "MISSING_MPI_CONFIG", "message": "MCNP execution requires --mpi-config."})
        return result

    staging = wd / "runner_inputs"; staging.mkdir(parents=True, exist_ok=True)
    for item, name in zip(ok_items, runner_files):
        shutil.copy2(Path(item["prepared_input_path"]), staging / name)
    result["runner_inputs_dir"] = str(staging)

    try:
        cfg_text = Path(mpi_config_path).read_text(encoding="utf-8")
        try:
            import yaml; mpi_cfg = yaml.safe_load(cfg_text)
        except ImportError:
            mpi_cfg = {}
    except OSError as exc:
        result["ok"] = False; result["dry_run"] = False
        result["errors"].append({"code": "MPI_CONFIG_LOAD_FAILED", "message": str(exc)})
        return result
    mpi_command = str(mpi_cfg.get("mpi_command", "")) if isinstance(mpi_cfg, dict) else ""

    try:
        runner_result = run_mpi_batch(target_dir=str(staging), mpi_command=mpi_command, dry_run=False, confirm=True, input_files=runner_files)
    except Exception as exc:
        result["ok"] = False; result["dry_run"] = False; result["run"]["status"] = "failed"
        result["errors"].append({"code": "RUNNER_FAILED", "message": str(exc)})
        return result
    if not runner_result.get("ok"):
        result["ok"] = False; result["dry_run"] = False; result["run"]["status"] = "failed"
        result["errors"].extend({"code": "RUNNER_ERROR", "message": str(e)} for e in runner_result.get("errors", []))
        return result

    result["ok"] = True; result["dry_run"] = False; result["executed"] = True
    result["run"]["status"] = "completed"
    result["run"]["runner_summary"] = {k: runner_result.get(k) for k in ("commands", "completed", "failed") if k in runner_result}

    if postprocess == "none":
        _write_sweep_manifest(wd, result, "run_disk_sweep_manifest.json")
        return result

    csv_base = Path(csv_dir) if csv_dir else wd / "postprocess_csv"; csv_base.mkdir(parents=True, exist_ok=True)
    plot_base = Path(plot_dir) if plot_dir else wd / "postprocess_plots"; plot_base.mkdir(parents=True, exist_ok=True)
    completed_runner = runner_result.get("completed", [])
    pp_ok = 0; pp_fail = 0

    for i, (item, name) in enumerate(zip(ok_items, runner_files)):
        mcnp_out = None
        if mcnp_outputs and i < len(mcnp_outputs): mcnp_out = mcnp_outputs[i]
        elif i < len(completed_runner): mcnp_out = completed_runner[i].get("output_path")
        # If no output path is available from any source, deliberately trigger MISSING_MCNP_OUTPUT
        if mcnp_out is None:
            mcnp_out = str(staging / "__nonexistent__.txt")
        stem_item = os.path.splitext(name)[0]
        pp = postprocess_workflow(input_path=Path(item["prepared_input_path"]), work_dir=item["work_dir"], mode=postprocess,
                                  mcnp_output_path=mcnp_out, csv_output_path=csv_base / f"{stem_item}.csv", plot_output_path=plot_base / f"{stem_item}.png")
        item["postprocess"] = {"ok": pp.get("ok"), "artifacts": pp.get("artifacts", {}), "blocked": pp.get("blocked", []), "errors": pp.get("errors", [])}
        if pp.get("ok"): pp_ok += 1
        else: pp_fail += 1

    result["postprocess_summary"] = {"succeeded": pp_ok, "failed": pp_fail}
    if pp_fail > 0 and pp_ok > 0: result["warnings"].append(f"Postprocess: {pp_ok} succeeded, {pp_fail} failed")
    elif pp_fail > 0 and pp_ok == 0: result["ok"] = False; result["errors"].append({"code": "POSTPROCESS_ALL_FAILED", "message": "Postprocess failed for all files"})

    _write_sweep_manifest(wd, result, "run_disk_sweep_manifest.json")
    return result


def _write_sweep_manifest(wd: Path, data: dict, name: str) -> None:
    try:
        path = wd / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        data.setdefault("artifacts", {})[f"{name.replace('.json', '')}_json"] = str(path)
    except OSError:
        pass
