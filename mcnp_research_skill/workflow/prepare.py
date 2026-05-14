"""Workflow preparation layer.

Reads an MCNP deck, inspects, plans, patches (NPS-only), and writes
artifacts to a work directory.  Does **not** run MCNP, extract CSV, or
generate plots.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..mcnp_input.inspection import inspect_deck
from ..mcnp_input.patching import patch_deck
from .planner import plan_workflow


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_workflow(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    workflow_mode: str,
    source_strategy: str | None = None,
    postprocess: str = "none",
    nps: str | int | float | None = None,
) -> dict[str, Any]:
    """Inspect → plan → patch/copy → artifact write.  No MCNP execution."""

    in_path = Path(input_path)
    wd = Path(work_dir)
    errors: list[str] = []
    warnings: list[str] = []

    # ---- read input ----
    if not in_path.exists():
        return {
            "ok": False,
            "input_path": str(in_path),
            "work_dir": str(wd),
            "errors": [f"File does not exist: {input_path}"],
            "warnings": [],
            "blocked": [],
        }

    try:
        text = in_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {
            "ok": False,
            "input_path": str(in_path),
            "work_dir": str(wd),
            "errors": [str(exc)],
            "warnings": [],
            "blocked": [],
        }

    # ---- inspect ----
    inspection = inspect_deck(text)

    # ---- plan ----
    plan = plan_workflow(
        inspection,
        workflow_mode=workflow_mode,
        source_strategy=source_strategy,
        postprocess=postprocess,
        requested_nps=nps,
    )

    # ---- prepare result skeleton ----
    prepared_name = in_path.name
    prepared_path = wd / prepared_name

    result: dict[str, Any] = {
        "ok": False,
        "schema_version": "1.0",
        "input_path": str(in_path),
        "work_dir": str(wd),
        "prepared_input_path": str(prepared_path),
        "workflow_mode": workflow_mode,
        "source_strategy": source_strategy or "preserve_existing_source",
        "postprocess": postprocess,
        "requested_nps": nps,
        "artifacts": {},
        "changed": False,
        "planned_actions": [],
        "blocked": [],
        "warnings": [],
        "errors": [],
    }

    # ---- create work dir ----
    try:
        wd.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result["errors"].append(str(exc))
        return result

    # ---- write inspection / plan (always, even on block) ----
    _write_json(wd / "inspection.json", inspection)
    _write_json(wd / "plan.json", plan)
    result["artifacts"]["inspection_json"] = str(wd / "inspection.json")
    result["artifacts"]["plan_json"] = str(wd / "plan.json")

    # ---- blocked → no prepared input ----
    if plan.get("blocked"):
        result["blocked"] = plan["blocked"]
        result["errors"] = [b.get("message", str(b)) for b in plan["blocked"]]
        result["warnings"] = plan.get("warnings", [])
        result["planned_actions"] = plan.get("actions", [])
        _write_json(wd / "manifest.json", result)
        result["artifacts"]["manifest_json"] = str(wd / "manifest.json")
        return result

    # ---- patch or copy ----
    effective_strategy = source_strategy or "preserve_existing_source"

    if nps is not None:
        patch_result = patch_deck(text, nps=nps, source_strategy=effective_strategy)
        if not patch_result.get("ok"):
            result["errors"].extend(
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in patch_result.get("errors", [])
            )
            result["blocked"] = patch_result.get("errors", [])
            _write_json(wd / "manifest.json", result)
            result["artifacts"]["manifest_json"] = str(wd / "manifest.json")
            return result
        patched_text = patch_result["text"]
        result["changed"] = True
        result["patch_summary"] = {
            "changed": True,
            "patches": patch_result.get("patches", []),
        }
        try:
            prepared_path.write_text(patched_text, encoding="utf-8")
        except OSError as exc:
            result["errors"].append(str(exc))
            return result
    else:
        try:
            shutil.copy2(in_path, prepared_path)
        except OSError as exc:
            result["errors"].append(str(exc))
            return result

    # ---- collect actions ----
    result["planned_actions"] = plan.get("actions", [])
    result["warnings"] = plan.get("warnings", [])
    result["errors"] = errors  # structural errors from this phase

    # ---- write manifest ----
    _write_json(wd / "manifest.json", result)
    result["artifacts"]["manifest_json"] = str(wd / "manifest.json")

    result["ok"] = True
    return result
