"""Workflow run layer.

Chains prepare_workflow → optional run-mpi execution without
re-implementing MPI logic.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..mcnp_run.mpi_runner import run_mpi_batch
from .prepare import prepare_workflow


def run_workflow(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    workflow_mode: str,
    source_strategy: str | None = None,
    postprocess: str = "none",
    nps: str | int | float | None = None,
    mpi_command: str | None = None,
    execute: bool = False,
    confirm_mpi: bool = False,
) -> dict[str, Any]:
    """Inspect → plan → patch/copy → (optionally) run MCNP."""

    result: dict[str, Any] = {
        "ok": False,
        "schema_version": "1.0",
        "dry_run": not execute,
        "executed": False,
        "prepare": {},
        "run": {"status": "not_started"},
        "postprocess_status": "not_requested" if postprocess == "none" else "planned_not_executed",
        "artifacts": {},
        "blocked": [],
        "warnings": [],
        "errors": [],
    }

    # ---- prepare ----
    prep = prepare_workflow(
        input_path=input_path,
        work_dir=work_dir,
        workflow_mode=workflow_mode,
        source_strategy=source_strategy,
        postprocess=postprocess,
        nps=nps,
    )
    result["prepare"] = {
        "ok": prep.get("ok"),
        "prepared_input_path": prep.get("prepared_input_path"),
        "changed": prep.get("changed", False),
    }
    result["artifacts"] = prep.get("artifacts", {})
    result["blocked"] = prep.get("blocked", [])
    result["warnings"] = prep.get("warnings", [])

    if not prep.get("ok"):
        result["errors"] = prep.get("errors", [])
        return result

    prepared_path = Path(prep.get("prepared_input_path", ""))
    input_name = prepared_path.name if prepared_path.name else Path(input_path).name
    work_path = Path(work_dir)

    # ---- dry-run ----
    if not execute:
        result["ok"] = True
        result["run"]["status"] = "skipped_dry_run"
        result["run"]["reason"] = "Pass --execute --confirm-mpi to run MCNP."
        return result

    # ---- execute safety gates ----
    if not confirm_mpi:
        result["ok"] = False
        result["dry_run"] = False
        result["errors"].append({
            "code": "MISSING_CONFIRM_MPI",
            "message": "Refusing to run MCNP without --confirm-mpi.",
        })
        return result

    if mpi_command is None:
        result["ok"] = False
        result["dry_run"] = False
        result["errors"].append({
            "code": "MISSING_MPI_CONFIG",
            "message": "MCNP execution requires --mpi-config / mpi_command.",
        })
        return result

    target_dir = str(work_path)

    # ---- call runner ----
    try:
        runner_result = run_mpi_batch(
            target_dir=target_dir,
            mpi_command=mpi_command,
            dry_run=False,
            confirm=True,
            input_files=[input_name],
        )
    except Exception as exc:
        result["ok"] = False
        result["dry_run"] = False
        result["run"]["status"] = "failed"
        result["errors"].append({
            "code": "RUNNER_FAILED",
            "message": str(exc),
        })
        return result

    if not runner_result.get("ok"):
        result["ok"] = False
        result["dry_run"] = False
        result["run"]["status"] = "failed"
        result["errors"].extend(
            {"code": "RUNNER_ERROR", "message": str(e)}
            for e in runner_result.get("errors", [])
        )
        result["warnings"].extend(runner_result.get("warnings", []))
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
    result["warnings"].extend(runner_result.get("warnings", []))
    return result
