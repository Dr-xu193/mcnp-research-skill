"""Point-source distance sweep preparation.

Generates multiple prepared MCNP decks from a single input by varying
the source position along an axis.  Only ``point_sdef_pos`` is supported.
Does **not** run MCNP, extract CSV, or plot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
