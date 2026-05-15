"""Confirmation-safe plan executor.

Bridges the output of :func:`~.nl_planner.plan_request` to actual
workflow execution.  Defaults to dry-run; real MCNP/MPI execution
requires ``--execute --confirm-user`` and a passing runtime preflight.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..mcnp_run.runtime import run_runtime_check


def _build_mpi_command(
    mpi_launcher: str | None,
    mcnp_exe: str | None,
    np: int | None,
    mpi_command: str | None,
    runtime: dict,
) -> dict[str, Any]:
    """Build the MPI command line from resolved parameters."""
    if mpi_command:
        return {
            "command": mpi_command,
            "source": "user_override",
            "preview": mpi_command,
        }

    launcher = mpi_launcher or (runtime["mpi_launcher"]["command"] if runtime["mpi_launcher"]["found"] else None)
    exe = mcnp_exe or (runtime["mcnp_executable"]["command"] if runtime["mcnp_executable"]["found"] else None)
    nprocs = np or runtime["recommended_np"]

    if launcher and exe:
        preview = f"{launcher} -np {nprocs} {exe}"
        return {"command": preview, "source": "runtime_preflight", "preview": preview, "launcher": launcher, "exe": exe, "np": nprocs}
    return {"command": None, "source": "runtime_preflight", "preview": None}


def execute_plan(
    plan: dict[str, Any],
    *,
    execute: bool = False,
    confirm_user: bool = False,
    np: int | None = None,
    mpi_launcher: str | None = None,
    mcnp_exe: str | None = None,
    mpi_command: str | None = None,
    work_dir: str | None = None,
) -> dict[str, Any]:
    """Execute a structured workflow plan, gated by confirmation and runtime checks.

    Parameters:
        plan: Output of :func:`~.nl_planner.plan_request`.
        execute: If True, actually run MCNP (requires confirm_user + preflight).
        confirm_user: User must explicitly confirm before real execution.
        np: Override MPI process count.
        mpi_launcher: Override MPI launcher.
        mcnp_exe: Override MCNP executable path.
        mpi_command: Expert override: full MPI command string.
        work_dir: Override work directory.

    Returns a structured result dict.
    """
    # ---- validate plan structure ----
    if not isinstance(plan, dict):
        return {
            "ok": False, "executed": False, "dry_run": not execute,
            "confirmation_required": True, "errors": [
                {"code": "PLAN_FILE_INVALID", "message": "Plan is not a valid JSON object."},
            ], "warnings": [],
        }

    result: dict[str, Any] = {
        "ok": False,
        "executed": False,
        "dry_run": not execute,
        "plan_status": plan.get("status", "unknown"),
        "workflow_command": plan.get("workflow_command", "unknown"),
        "confirmation_required": True,
        "errors": [],
        "warnings": [],
    }

    if not plan.get("workflow_command"):
        result["errors"].append({"code": "PLAN_FILE_INVALID", "message": "Plan missing workflow_command."})
        return result

    # ---- check plan status ----
    status = plan.get("status", "unknown")
    if status in ("needs_clarification", "blocked"):
        errs = plan.get("errors", [])
        result["errors"].append({
            "code": "PLAN_NOT_EXECUTABLE",
            "message": f"Plan status is '{status}'. Resolve the issues first.",
            "plan_errors": errs,
        })
        return result

    # ---- check missing required ----
    missing = plan.get("missing_required", [])
    if missing:
        result["errors"].append({
            "code": "PLAN_MISSING_REQUIRED",
            "message": f"Plan is missing required parameters: {missing}",
            "missing": missing,
        })
        return result

    # ---- runtime preflight ----
    runtime = run_runtime_check(np=np, mpi_launcher=mpi_launcher, mcnp_exe=mcnp_exe)
    result["runtime_preflight"] = runtime

    # ---- build MPI command ----
    mpi_info = _build_mpi_command(mpi_launcher, mcnp_exe, np, mpi_command, runtime)
    result["command_preview"] = mpi_info["preview"]

    # ---- execution gates ----
    if execute:
        # Gate 1: user confirmation
        if not confirm_user:
            result["errors"].append({
                "code": "USER_CONFIRMATION_REQUIRED",
                "message": "真实运行需要 --confirm-user。请先确认 plan 的理解正确。",
            })
            return result

        # Gate 2: MCNP executable
        if not mpi_command and not runtime["mcnp_executable"]["found"] and not mcnp_exe:
            result["errors"].append({
                "code": "MCNP_NOT_FOUND",
                "message": "MCNP executable not found. Install MCNP or specify --mcnp-exe.",
            })
            return result

        # Gate 3: MPI launcher
        if not mpi_command and not runtime["mpi_launcher"]["found"] and not mpi_launcher:
            result["errors"].append({
                "code": "MPI_LAUNCHER_NOT_FOUND",
                "message": "MPI launcher not found. Install MPI or specify --mpi-launcher.",
            })
            return result

    # ---- map plan to workflow ----
    wf_cmd = plan.get("workflow_command", "")
    wf_result = _dispatch_workflow(plan, execute=execute, work_dir=work_dir, mpi_command=mpi_info["command"] if execute else None)

    result["ok"] = wf_result.get("ok", False)
    result["workflow_result"] = wf_result
    if execute and wf_result.get("ok"):
        result["executed"] = wf_result.get("executed", False)
    result["warnings"].extend(wf_result.get("warnings", []))
    for e in wf_result.get("errors", []):
        if isinstance(e, dict):
            result["errors"].append(e)
        else:
            result["errors"].append({"message": str(e)})

    # ---- failure analysis integration (lightweight) ----
    if execute and not wf_result.get("ok"):
        from ..mcnp_output.failure_analyzer import analyze_mcnp_failure
        output_text = wf_result.get("output_text") or wf_result.get("output")
        stdout_text = wf_result.get("stdout_text") or wf_result.get("stdout")
        stderr_text = wf_result.get("stderr_text") or wf_result.get("stderr")
        rc = wf_result.get("returncode", 1)
        if output_text or stdout_text or stderr_text:
            fa = analyze_mcnp_failure(
                output_text=output_text,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                returncode=rc,
                context=plan,
                front_lines=300,
                tail_lines=120,
            )
            result["failure_analysis"] = fa

    return result


def _dispatch_workflow(
    plan: dict[str, Any],
    *,
    execute: bool,
    work_dir: str | None,
    mpi_command: str | None,
) -> dict[str, Any]:
    """Map a plan to the correct workflow function and call it."""
    wf_cmd = plan.get("workflow_command", "")
    model = plan.get("model", "")
    source_strategy = plan.get("source_strategy") or "point_sdef_pos"
    postprocess = plan.get("postprocess", "none")
    nps = plan.get("nps")
    source_energy = plan.get("source_energy")
    source_radius = plan.get("source_radius")
    rp_position = plan.get("reference_position")
    distances = plan.get("distance", {}) or {}
    dist_list = distances.get("distances")
    start = distances.get("start")
    stop = distances.get("stop")
    step = distances.get("step")
    ref_pos = rp_position or [0.0, 0.0, 0.0]

    # Resolve input path
    from ..models.registry import resolve_deck_path as _resolve_deck

    input_path: str
    try:
        input_path = str(_resolve_deck(model))
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "errors": [{"code": "MODEL_NOT_FOUND", "message": str(e)}]}

    wd = work_dir or f"runs/{model}_{wf_cmd}"
    intent = plan.get("intent", "")

    # ---- GEB fit commands ----
    if intent in ("fit_geb", "fit_geb_and_patch", "patch_geb", "fit_geb_patch_and_run_sweep"):
        spe_files = plan.get("spe_files", [])
        if not spe_files:
            return {"ok": False, "errors": [{"code": "MISSING_SPE_FILES",
                "message": "缺少 SPE 文件。请提供用于拟合 GEB 的能谱文件。"}]}
        # Run GEB fit
        from ..geb.spe import fit_geb_from_spe_files
        geb = fit_geb_from_spe_files(spe_files)
        if not geb.get("geb_fit_ok"):
            return geb  # returns fit result with errors

        # Handle patch
        if intent in ("fit_geb_and_patch", "fit_geb_patch_and_run_sweep", "patch_geb"):
            from pathlib import Path
            from ..mcnp_input.patching import patch_geb as _patch_geb
            a, b, c = geb["fitted_params"]["A"], geb["fitted_params"]["B"], geb["fitted_params"]["C"]
            deck_text = Path(input_path).read_text(encoding="utf-8")
            patch_r = _patch_geb(deck_text, a, b, c)
            geb["patch_result"] = patch_r
            if patch_r["ok"]:
                patched = Path(wd) / f"{model}_geb_patched.txt"
                patched.parent.mkdir(parents=True, exist_ok=True)
                patched.write_text(patch_r["text"], encoding="utf-8")
                geb["patched_deck_path"] = str(patched)
            else:
                return geb  # patch failed (e.g., no F8)
        if intent == "fit_geb":
            return geb

        # If sweep after GEB, continue to sweep dispatch
        if intent == "fit_geb_patch_and_run_sweep":
            input_path = geb.get("patched_deck_path", input_path)

    # ---- sweep commands ----
    if wf_cmd in ("run-point-sweep", "prepare-point-sweep", "run-disk-sweep", "prepare-disk-sweep"):
        from ..workflow.sweep import (
            prepare_disk_sweep,
            prepare_point_sweep,
            run_disk_sweep,
            run_point_sweep,
        )

        # Build kwargs for sweep functions
        _common: dict[str, Any] = {
            "input_path": input_path,
            "work_dir": wd,
            "axis": "z",
            "direction": 1,
            "source_energy": source_energy,
            "source_particle": None,
            "nps": str(nps) if nps else None,
            "postprocess": postprocess,
            "reference_position": ref_pos,
        }
        if dist_list:
            _common["distances"] = dist_list
        else:
            _common["start"] = start
            _common["stop"] = stop
            _common["step"] = step

        if source_strategy == "disk_tr1":
            _common["source_radius"] = source_radius
            if wf_cmd.startswith("run-"):
                _common["execute"] = execute
                _common["confirm_mpi"] = execute
                _common["mpi_config_path"] = None
                # run_disk_sweep has extra params
                _common.setdefault("source_ext", 0)
                _common.setdefault("source_card_id", None)
                _common.setdefault("mcnp_outputs", None)
                _common.setdefault("csv_dir", None)
                _common.setdefault("plot_dir", None)
                return run_disk_sweep(**{k: v for k, v in _common.items()
                    if k in ("input_path", "work_dir", "distances", "start", "stop", "step",
                             "axis", "reference_position", "direction", "source_energy",
                             "source_radius", "source_particle", "source_ext", "source_card_id",
                             "nps", "postprocess", "mpi_config_path", "execute", "confirm_mpi",
                             "mcnp_outputs", "csv_dir", "plot_dir")})
            return prepare_disk_sweep(**{k: v for k, v in _common.items()
                if k in ("input_path", "work_dir", "distances", "start", "stop", "step",
                         "axis", "reference_position", "direction", "source_energy",
                         "source_radius", "source_particle", "source_ext", "source_card_id",
                         "nps", "postprocess")})
        else:
            if wf_cmd.startswith("run-"):
                _common["execute"] = execute
                _common["confirm_mpi"] = execute
                _common["mpi_config_path"] = None
                _common.setdefault("mcnp_outputs", None)
                _common.setdefault("csv_dir", None)
                _common.setdefault("plot_dir", None)
                return run_point_sweep(**{k: v for k, v in _common.items()
                    if k in ("input_path", "work_dir", "distances", "start", "stop", "step",
                             "axis", "reference_position", "direction", "source_energy",
                             "source_particle", "nps", "postprocess", "mpi_config_path",
                             "execute", "confirm_mpi", "mcnp_outputs", "csv_dir", "plot_dir")})
            return prepare_point_sweep(**{k: v for k, v in _common.items()
                if k in ("input_path", "work_dir", "distances", "start", "stop", "step",
                         "axis", "reference_position", "direction", "source_energy",
                         "source_particle", "nps", "postprocess")})

    # ---- diagnose ----
    if wf_cmd == "diagnose-deck":
        from ..mcnp_input.diagnostics import diagnose_deck_file
        return diagnose_deck_file(input_path)

    # ---- run-only / batch ----
    if wf_cmd in ("run-workflow", "batch-workflow"):
        from ..workflow.run import run_workflow
        run_kwargs: dict[str, Any] = {
            "input_path": input_path,
            "work_dir": wd,
            "workflow_mode": "run-only",
            "source_strategy": source_strategy or "preserve_existing_source",
            "postprocess": postprocess,
            "nps": str(nps) if nps else None,
            "execute": execute,
            "confirm_mpi": execute,
            "mpi_command": mpi_command,
        }
        if source_strategy in ("point_sdef_pos", "disk_tr1") and rp_position and source_energy:
            run_kwargs["source_position"] = tuple(rp_position)
            run_kwargs["source_energy"] = source_energy
            if source_radius:
                run_kwargs["source_radius"] = source_radius
        return run_workflow(**run_kwargs)

    if wf_cmd == "postprocess-workflow":
        from ..workflow.postprocess import postprocess_workflow
        return postprocess_workflow(
            input_path=input_path,
            work_dir=Path(wd),
            mode=postprocess if postprocess != "none" else "csv",
        )

    return {"ok": False, "errors": [{"code": "PLAN_COMMAND_UNSUPPORTED",
        "message": f"Workflow command '{wf_cmd}' is not yet supported for execute-plan."}]}
