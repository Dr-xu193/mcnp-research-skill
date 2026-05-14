"""Batch workflow for existing MCNP deck directories.

Scans an input directory for ``*.txt`` files, runs ``prepare_workflow``
on each one, collects per-file results, and optionally invokes the
MPI runner on the prepared decks (via Phase 3E ``input_files``).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from ..mcnp_run.mpi_runner import run_mpi_batch
from .prepare import prepare_workflow


def _scan_txt_files(input_dir: Path) -> list[str]:
    """Return sorted ``*.txt`` file names in *input_dir* (name only)."""
    try:
        names = sorted(
            f.name for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() == ".txt"
        )
    except OSError:
        return []
    return names


def _safe_subdir_path(work_dir: Path, stem: str, used: set[str]) -> Path:
    """Return a unique subdirectory path for *stem*."""
    candidate = stem
    counter = 1
    while candidate in used:
        counter += 1
        candidate = f"{stem}_{counter}"
    used.add(candidate)
    return work_dir / candidate


def batch_workflow(
    *,
    input_dir: str | Path,
    work_dir: str | Path,
    workflow_mode: str = "run-only",
    source_strategy: str | None = None,
    postprocess: str = "none",
    nps: str | int | float | None = None,
    input_files: list[str] | None = None,
    mpi_config_path: str | Path | None = None,
    execute: bool = False,
    confirm_mpi: bool = False,
) -> dict[str, Any]:
    """Scan *input_dir* for ``*.txt`` files, prepare each, and optionally run."""

    in_dir = Path(input_dir)
    wd = Path(work_dir)
    errors: list[dict] = []
    warnings: list[str] = []

    # ---- input files ----
    if not in_dir.exists() or not in_dir.is_dir():
        return {
            "ok": False, "schema_version": "1.0",
            "input_dir": str(in_dir), "work_dir": str(wd),
            "errors": [{"code": "INPUT_DIR_NOT_FOUND", "message": f"Input directory does not exist: {input_dir}"}],
            "warnings": [],
        }

    if input_files is not None:
        file_names = [f for f in input_files if (in_dir / f).is_file()]
    else:
        file_names = _scan_txt_files(in_dir)

    if not file_names:
        return {
            "ok": False, "schema_version": "1.0",
            "input_dir": str(in_dir), "work_dir": str(wd),
            "total_files": 0,
            "errors": [{"code": "NO_INPUT_FILES", "message": f"No .txt files found in {input_dir}"}],
            "warnings": [],
        }

    # ---- prepare each file ----
    wd.mkdir(parents=True, exist_ok=True)
    used_stems: set[str] = set()
    per_file: list[dict[str, Any]] = []
    prepared_count = 0
    blocked_count = 0

    for fname in file_names:
        stem = Path(fname).stem
        subdir = _safe_subdir_path(wd, stem, used_stems)
        prep = prepare_workflow(
            input_path=in_dir / fname,
            work_dir=subdir,
            workflow_mode=workflow_mode,
            source_strategy=source_strategy,
            postprocess=postprocess,
            nps=nps,
        )
        entry: dict[str, Any] = {
            "input_file": fname,
            "ok": prep.get("ok", False),
            "prepared_input_path": prep.get("prepared_input_path"),
            "work_dir": str(subdir),
            "blocked": prep.get("blocked", []),
            "changed": prep.get("changed", False),
            "errors": prep.get("errors", []),
            "warnings": prep.get("warnings", []),
        }
        if entry["ok"]:
            prepared_count += 1
        elif entry["blocked"]:
            blocked_count += 1
        per_file.append(entry)
        errors.extend(
            {"code": "FILE_ERROR", "file": fname, "message": str(e)}
            for e in entry["errors"] if isinstance(e, str)
        )

    any_ok = any(e["ok"] for e in per_file)

    result: dict[str, Any] = {
        "ok": any_ok,
        "schema_version": "1.0",
        "dry_run": not execute,
        "executed": False,
        "input_dir": str(in_dir),
        "work_dir": str(wd),
        "workflow_mode": workflow_mode,
        "source_strategy": source_strategy or "preserve_existing_source",
        "postprocess": postprocess,
        "requested_nps": nps,
        "total_files": len(file_names),
        "prepared_count": prepared_count,
        "blocked_count": blocked_count,
        "failed_count": len(file_names) - prepared_count,
        "per_file_results": per_file,
        "artifacts": {},
        "run": {"status": "not_started"},
        "warnings": warnings,
        "errors": [],
    }

    # ---- batch manifest (always write) ----
    manifest_path = wd / "batch_manifest.json"
    try:
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["artifacts"]["batch_manifest_json"] = str(manifest_path)
    except OSError:
        pass

    if not any_ok:
        if blocked_count == len(file_names):
            result["errors"] = [{"code": "ALL_BLOCKED", "message": "All input files were blocked"}]
        return result

    # ---- dry-run → done ----
    if not execute:
        result["run"]["status"] = "skipped_dry_run"
        result["runner_input_files"] = [Path(e["prepared_input_path"]).name for e in per_file if e["ok"]]
        return result

    # ---- execute safety gates ----
    if not confirm_mpi:
        result["ok"] = False
        result["dry_run"] = False
        result["errors"].append({"code": "MISSING_CONFIRM_MPI", "message": "Refusing to run MCNP without --confirm-mpi."})
        return result

    if mpi_config_path is None:
        result["ok"] = False
        result["dry_run"] = False
        result["errors"].append({"code": "MISSING_MPI_CONFIG", "message": "MCNP execution requires --mpi-config."})
        return result

    # ---- stage prepared decks for runner ----
    staging = wd / "runner_inputs"
    staging.mkdir(parents=True, exist_ok=True)
    runner_names: list[str] = []
    used: set[str] = set()
    for entry in per_file:
        if not entry["ok"]:
            continue
        src = Path(entry["prepared_input_path"])
        name = src.name
        if name in used:
            stem, ext = os.path.splitext(name)
            counter = 2
            while (candidate := f"{stem}_{counter}{ext}") in used:
                counter += 1
            name = candidate
        used.add(name)
        runner_names.append(name)
        shutil.copy2(src, staging / name)

    result["runner_inputs_dir"] = str(staging)
    result["runner_input_files"] = runner_names

    # ---- load MPI config ----
    try:
        cfg_text = Path(mpi_config_path).read_text(encoding="utf-8")
        try:
            import yaml
            mpi_cfg = yaml.safe_load(cfg_text)
        except ImportError:
            mpi_cfg = {}
    except OSError as exc:
        result["ok"] = False
        result["errors"].append({"code": "MPI_CONFIG_LOAD_FAILED", "message": str(exc)})
        return result

    mpi_command = str(mpi_cfg.get("mpi_command", "")) if isinstance(mpi_cfg, dict) else ""

    # ---- call runner ----
    try:
        runner_result = run_mpi_batch(
            target_dir=str(staging),
            mpi_command=mpi_command,
            dry_run=False,
            confirm=True,
            input_files=runner_names,
        )
    except Exception as exc:
        result["ok"] = False
        result["dry_run"] = False
        result["run"]["status"] = "failed"
        result["errors"].append({"code": "RUNNER_FAILED", "message": str(exc)})
        return result

    if not runner_result.get("ok"):
        result["ok"] = False
        result["dry_run"] = False
        result["run"]["status"] = "failed"
        result["errors"].extend(
            {"code": "RUNNER_ERROR", "message": str(e)}
            for e in runner_result.get("errors", [])
        )
        return result

    result["ok"] = True
    result["dry_run"] = False
    result["executed"] = True
    result["run"]["status"] = "completed"
    result["run"]["runner_summary"] = {
        k: runner_result.get(k)
        for k in ("commands", "completed", "failed")
        if k in runner_result
    }
    return result
