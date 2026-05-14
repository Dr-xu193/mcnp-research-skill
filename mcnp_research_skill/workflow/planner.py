"""Workflow preflight planner.

Consumes an ``inspect_deck`` result and produces a structured plan with
actions, capabilities, and blocking conditions.  Does **not** modify
files, run MCNP, or invoke post-processing.
"""

from __future__ import annotations

from typing import Any

VALID_WORKFLOW_MODES = {"run-only", "patch-and-run", "generate-and-run"}
VALID_SOURCE_STRATEGIES = {
    "preserve_existing_source",
    "point_sdef_pos",
    "point_tr1",
    "disk_tr1",
    "encapsulated_disk_tr1",
    "custom_source_block",
}
VALID_POSTPROCESS = {"none", "csv", "plot", "csv-and-plot"}


def _has_f8(tallies: list[dict]) -> bool:
    return any(t.get("kind") == "F8" for t in tallies)


def _has_any_tally(tallies: list[dict]) -> bool:
    return len(tallies) > 0


def _blocked(entry: str, message: str) -> dict:
    return {"code": entry, "message": message}


def plan_workflow(
    inspection: dict,
    *,
    workflow_mode: str,
    source_strategy: str | None = None,
    postprocess: str = "none",
    requested_nps: str | int | float | None = None,
) -> dict[str, Any]:
    """Plan a workflow from an inspection report."""

    # ---- validate inputs ----
    errors: list[str] = []
    if workflow_mode not in VALID_WORKFLOW_MODES:
        errors.append(f"Invalid workflow_mode '{workflow_mode}'; must be one of {sorted(VALID_WORKFLOW_MODES)}")
    if source_strategy is not None and source_strategy not in VALID_SOURCE_STRATEGIES:
        errors.append(f"Invalid source_strategy '{source_strategy}'; must be one of {sorted(VALID_SOURCE_STRATEGIES)}")
    if postprocess not in VALID_POSTPROCESS:
        errors.append(f"Invalid postprocess '{postprocess}'; must be one of {sorted(VALID_POSTPROCESS)}")

    nps_value: float | None = None
    if requested_nps is not None:
        try:
            nps_value = float(str(requested_nps).lower().replace("d", "e"))
        except ValueError:
            errors.append(f"Invalid requested_nps: {requested_nps!r}")

    if errors:
        return {
            "ok": False,
            "schema_version": "1.0",
            "workflow_mode": workflow_mode,
            "source_strategy": source_strategy,
            "postprocess": postprocess,
            "warnings": [],
            "errors": errors,
            "blocked": [],
            "capabilities": {},
            "actions": [],
        }

    result: dict[str, Any] = {
        "ok": True,
        "schema_version": "1.0",
        "workflow_mode": workflow_mode,
        "source_strategy": source_strategy or "preserve_existing_source",
        "postprocess": postprocess,
        "requested_nps": nps_value,
        "preflight": {
            "has_errors": False,
            "errors": [],
            "warnings": [],
        },
        "capabilities": {},
        "actions": [{"step": "inspect", "status": "done"}],
        "blocked": [],
        "warnings": [],
        "errors": [],
    }

    blocked: list[dict] = result["blocked"]
    warnings: list[str] = result["warnings"]
    actions: list[dict] = result["actions"]

    inspect_errors: list[dict | str] = inspection.get("errors", [])
    inspect_warnings: list[str] = inspection.get("warnings", [])
    tallies: list[dict] = inspection.get("tallies", [])
    nps_info: dict = inspection.get("nps", {})
    nps_present: bool = nps_info.get("present", False)
    nps_lines: list[int] = nps_info.get("lines", [])

    needs_patch = workflow_mode in {"patch-and-run", "generate-and-run"}

    # ---- source_strategy ----
    if needs_patch and (source_strategy is None or source_strategy == ""):
        blocked.append(_blocked("MISSING_SOURCE_STRATEGY", "patch-and-run / generate-and-run requires an explicit source_strategy"))

    # ---- NPS ----
    if len(nps_lines) > 1:
        blocked.append(_blocked("MULTIPLE_NPS", f"Multiple NPS cards at lines {nps_lines}"))
    elif not nps_present:
        if nps_value is not None:
            actions.append({"step": "patch_nps", "status": "planned", "value": nps_value, "reason": "requested_nps provided"})
        else:
            warnings.append("No NPS card detected; injection may be needed before execution")
    elif nps_present and nps_value is not None:
        current_nps = nps_info.get("value")
        actions.append({"step": "patch_nps", "status": "planned", "current": current_nps, "target": nps_value, "reason": "requested_nps differs from existing"})

    # ---- postprocess ----
    wants_csv = postprocess in {"csv", "csv-and-plot"}
    wants_plot = postprocess in {"plot", "csv-and-plot"}
    can_csv = False
    can_plot = False

    if wants_csv or wants_plot:
        if not _has_any_tally(tallies):
            blocked.append(_blocked("NO_SUPPORTED_TALLY_FOR_CSV", "No tally cards found; CSV extraction / plotting requires at least one F8 tally"))
        elif not _has_f8(tallies):
            blocked.append(_blocked("CSV_REQUIRES_F8", "CSV extraction/plotting currently supports only F8 pulse-height tally"))
        else:
            can_csv = True
            can_plot = wants_plot

    can_run = not any(b.get("code") in ("MULTIPLE_NPS", "MISSING_SOURCE_STRATEGY") for b in blocked)

    result["capabilities"] = {
        "can_run": can_run,
        "can_extract_csv": can_csv,
        "can_plot": can_plot,
        "can_patch": needs_patch,
        "csv_plot_requires_f8": True,
    }

    # ---- build actions ----
    if can_run:
        actions.append({"step": "run", "status": "planned", "reason": f"{workflow_mode} workflow requested"})
    if can_csv:
        actions.append({"step": "extract_csv", "status": "planned"})
    if can_plot:
        actions.append({"step": "plot_spectra", "status": "planned"})

    # ---- pass through inspection warnings ----
    for w in inspect_warnings:
        warnings.append(w)

    # ---- re-evaluate ok ----
    result["preflight"]["errors"] = inspect_errors
    result["preflight"]["warnings"] = inspect_warnings
    result["preflight"]["has_errors"] = bool(inspect_errors or blocked)

    result["ok"] = not blocked and not errors
    result["warnings"] = warnings

    return result
