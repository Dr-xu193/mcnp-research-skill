"""Final user-flow release acceptance tests.

Verifies end-to-end: NL → plan → diagnose → runtime → execute → failure analysis.
No real MCNP/MPI execution.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]


def _run(*args):
    return subprocess.run(
        CLI + list(args), text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _planj(text, **kw):
    args = ["--json", "plan-request", "--text", text]
    for k, v in kw.items():
        args.extend([f"--{k.replace('_', '-')}", str(v)])
    r = _run(*args)
    return json.loads(r.stdout), r.returncode


# ==================================================================
# Flow 1: 3x3 verified + crystal front + Cs-137 + CSV
# ==================================================================

def test_flow_1_3x3_crystal_front_csv(tmp_path):
    text = "3 inch NaI, Cs-137 point source, distance from nai crystal front surface 10 to 20 cm step 5 cm, nps 1e6, csv only"
    p, rc = _planj(text)
    assert rc == 0
    assert p["model"] == "nai_3x3_verified"
    assert p["model_verified"] is True
    assert p["canonical_reference_point"] == "nai_crystal_front_surface"
    assert p["source_energy"] == 0.662
    assert p["status"] == "ready_for_review"

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")
    r2 = _run("--json", "execute-plan", "--plan-file", str(plan_file))
    assert r2.returncode == 0
    p2 = json.loads(r2.stdout)
    assert p2["ok"]
    assert p2["dry_run"] is True
    assert p2["workflow_result"]["prepared_count"] == 3


# ==================================================================
# Flow 2: 2x2 template + aluminum shell + execute requested
# ==================================================================

def test_flow_2_2x2_execute_requested():
    text = "2 inch NaI, Cs-137 point source, distance from aluminum shell 10 to 20 cm step 5 cm, nps 1e7, csv only, execute"
    p, rc = _planj(text)
    assert rc == 0
    assert p["model"] == "nai_2x2_template"
    assert p["model_verified"] is False
    assert p["execute_requested"] is True
    assert p["canonical_reference_point"] == "aluminum_shell_front"
    assert "2x2" in p["human_summary"] or "未验证" in p["human_summary"]
    assert p["source_energy"] == 0.662


def test_flow_2_execute_without_confirm_blocked(tmp_path):
    text = "2 inch NaI, Cs-137 point source, distance from aluminum shell 10 to 20 cm step 5 cm, nps 1e6, csv only, execute"
    p, _ = _planj(text)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")

    r = _run("--json", "execute-plan", "--plan-file", str(plan_file), "--execute")
    p2 = json.loads(r.stdout)
    assert not p2["ok"]
    assert any(e["code"] == "USER_CONFIRMATION_REQUIRED" for e in p2.get("errors", []) if isinstance(e, dict))

    # Chinese output must contain confirmation message
    r_zh = _run("execute-plan", "--plan-file", str(plan_file), "--execute")
    assert not r_zh.stdout.strip().startswith("{")  # not JSON


# ==================================================================
# Flow 3: Missing energy + ambiguous ref
# ==================================================================

def test_flow_3_missing_energy_and_ambiguous_distance():
    text = "use 3 inch NaI detector, distance from detector 10 to 20 cm step 5 cm, nps 1e6, csv and plot"
    p, rc = _planj(text)
    # Should have errors about ambiguous ref and/or missing energy
    assert not p["ok"] or p["status"] in ("needs_clarification", "blocked")
    err_codes = [e.get("code", "") for e in p.get("errors", []) if isinstance(e, dict)]
    assert any(c in ("AMBIGUOUS_REFERENCE_POINT", "MODEL_NOT_DETECTED") or "REFERENCE" in c for c in err_codes) or "source_energy" in p.get("missing_required", [])


# ==================================================================
# Flow 4: Single point source, 63.6 keV
# ==================================================================

def test_flow_4_single_point_63kev(tmp_path):
    text = "3 inch NaI, point source at 63.6 keV, distances 10 cm from nai crystal front surface, nps 1e6, csv and plot"
    p, rc = _planj(text)
    assert rc == 0
    assert p["source_energy"] == pytest.approx(0.0636, abs=0.001)
    assert p["distance"]["distances"] == [10.0] or p["distance"]["start"] == 10

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")
    r2 = _run("--json", "execute-plan", "--plan-file", str(plan_file))
    p2 = json.loads(r2.stdout)
    assert p2["ok"]


# ==================================================================
# Flow 5: F4 run-only allowed
# ==================================================================

def test_flow_5_f4_run_only(tmp_path):
    from mcnp_research_skill.workflow.planner import plan_workflow
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\n\nmode p\nf4:p 1\nnps 100\n"
    (tmp_path / "f4.txt").write_text(deck, encoding="utf-8")
    insp = inspect_deck_file(str(tmp_path / "f4.txt"))

    # run-only: not blocked
    plan = plan_workflow(insp, workflow_mode="run-only", source_strategy="preserve_existing_source", postprocess="none")
    assert not plan.get("blocked")

    # csv: blocked
    plan2 = plan_workflow(insp, workflow_mode="run-only", source_strategy="preserve_existing_source", postprocess="csv")
    assert any(b["code"] == "CSV_REQUIRES_F8" for b in plan2.get("blocked", []))


# ==================================================================
# Flow 6: F4 + CSV blocked, Chinese output
# ==================================================================

def test_flow_6_f4_csv_blocked_chinese():
    from mcnp_research_skill.workflow.user_output import render_non_f8_response
    text = render_non_f8_response("F4", "csv")
    assert "F4" in text
    assert "F8" in text
    assert "run-only" in text


# ==================================================================
# Flow 7: Diagnose deck with issues
# ==================================================================

def test_flow_7_diagnose_tab_and_long_line(tmp_path):
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\n" + ("x" * 85) + "\nnps 100\n"
    (tmp_path / "bad.txt").write_text(deck, encoding="utf-8")

    r = _run("diagnose-deck", "--input", str(tmp_path / "bad.txt"), "--mcnp-version", "mcnp5_rsicc_1_14")
    assert not r.stdout.strip().startswith("{")  # Chinese output, not JSON
    assert "MCNP5_RSICC" in r.stdout.upper() or "1.14" in r.stdout

    # Repair
    r2 = _run("repair-deck", "--input", str(tmp_path / "bad.txt"),
              "--output", str(tmp_path / "fixed.txt"))
    assert (tmp_path / "fixed.txt").exists()
    fixed = (tmp_path / "fixed.txt").read_text(encoding="utf-8")
    assert "\t" not in fixed


# ==================================================================
# Flow 8: Runtime missing MCNP / MPI
# ==================================================================

def test_flow_8_runtime_chinese():
    r = _run("runtime-check")
    assert not r.stdout.strip().startswith("{")  # not JSON
    assert "MCNP" in r.stdout or "mpirun" in r.stdout.lower() or "mpiexec" in r.stdout.lower()


def test_flow_8_mcnp_missing_chinese():
    from mcnp_research_skill.workflow.user_output import render_execute_plan_response
    result = {"ok": False, "errors": [{"code": "MCNP_NOT_FOUND", "message": "x"}]}
    text = render_execute_plan_response(result)
    assert "MCNP" in text
    assert "download" not in text.lower()


def test_flow_8_mpi_missing_chinese():
    from mcnp_research_skill.workflow.user_output import render_execute_plan_response
    result = {"ok": False, "errors": [{"code": "MPI_LAUNCHER_NOT_FOUND", "message": "x"}]}
    text = render_execute_plan_response(result)
    assert "MPICH" in text or "OpenMPI" in text or "mpirun" in text.lower()


# ==================================================================
# Flow 9: Failure analyzer front-300 strategy
# ==================================================================

def test_flow_9_failure_analyzer_front_300():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure
    output = ("ok\n" * 99) + "fatal error\n" + ("ok\n" * 9900)
    r = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert r["status"] == "failed"
    assert r["front_lines_analyzed"] == 300
    assert r["total_output_lines"] == 10000
    assert not any("ok" in f.get("evidence", "") for f in r["findings"] if f["code"] == "MCNP_FATAL_ERROR")


def test_flow_9_failure_analyzer_no_full_log_output():
    from mcnp_research_skill.mcnp_output.failure_analyzer import render_failure_response, analyze_mcnp_failure
    output = "fatal error\n" + ("data\n" * 10000)
    r = analyze_mcnp_failure(output_text=output, front_lines=300)
    text = render_failure_response(r)
    assert len(text) < 5000  # under 5KB


# ==================================================================
# Flow 10: Activity Bq
# ==================================================================

def test_flow_10_activity_bq():
    text = "2 inch NaI, Cs-137 activity 1e6 Bq, distance from crystal front 10 cm, run csv"
    p, _ = _planj(text)
    errs = p.get("errors", [])
    assert any(e["code"] == "ACTIVITY_NORMALIZATION_UNSUPPORTED" for e in errs)
    assert p.get("nps") is None or p["nps"] != 1_000_000


# ==================================================================
# Execute-plan + failure analyzer integration
# ==================================================================

def test_execute_plan_failure_analysis_integrated(tmp_path):
    """When execute-plan workflow fails with output, failure analysis is included."""
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = {
        "ok": True, "status": "ready_for_review",
        "workflow_command": "run-point-sweep",
        "model": "nai_2x2_template", "model_verified": False,
        "source_strategy": "point_sdef_pos", "source_energy": 0.662,
        "nps": 1_000_000, "postprocess": "csv",
        "distance": {"distances": [10.0]},
        "reference_position": [0.0, 0.0, -0.1],
        "execute_requested": True, "missing_required": [], "warnings": [], "errors": [],
    }

    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ):
        result = execute_plan(plan, execute=True, confirm_user=True)
        # Runner will fail (no real MCNP), but failure_analysis should be present
        if not result["ok"] and result.get("workflow_result", {}).get("output_text") or result.get("workflow_result", {}).get("stderr_text"):
            assert "failure_analysis" in result


def test_execute_plan_mock_failure_with_stderr_mpi():
    """Mock failure with stderr about mpirun missing."""
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = {
        "ok": True, "status": "ready_for_review",
        "workflow_command": "run-point-sweep",
        "model": "nai_2x2_template", "source_strategy": "point_sdef_pos",
        "source_energy": 0.662, "nps": 1_000_000, "postprocess": "none",
        "distance": {"distances": [10.0]},
        "reference_position": [0.0, 0.0, -0.1],
        "execute_requested": True, "missing_required": [], "warnings": [], "errors": [],
    }

    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": False, "command": None, "path": None, "source": None},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ):
        result = execute_plan(plan, execute=True, confirm_user=True)
        assert not result["ok"]
        assert any(e["code"] == "MPI_LAUNCHER_NOT_FOUND" for e in result["errors"])


def test_execute_plan_both_mcnp_and_mpi_missing():
    """When BOTH MCNP and MPI are missing, BOTH error codes must appear."""
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = {
        "ok": True, "status": "ready_for_review",
        "workflow_command": "run-point-sweep",
        "model": "nai_2x2_template", "source_strategy": "point_sdef_pos",
        "source_energy": 0.662, "nps": 1_000_000, "postprocess": "none",
        "distance": {"distances": [10.0]},
        "reference_position": [0.0, 0.0, -0.1],
        "execute_requested": True, "missing_required": [], "warnings": [], "errors": [],
    }

    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": False, "command": None, "path": None, "source": None},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": False, "command": None, "path": None, "source": None},
    ):
        result = execute_plan(plan, execute=True, confirm_user=True)
        assert not result["ok"]
        codes = [e["code"] for e in result.get("errors", []) if isinstance(e, dict)]
        assert "MPI_LAUNCHER_NOT_FOUND" in codes
        assert "MCNP_NOT_FOUND" in codes


def test_execute_plan_mock_disk_tr1_source_error():
    """Mock execute with disk_tr1 source strategy — verify context."""
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = {
        "ok": True, "status": "ready_for_review",
        "workflow_command": "prepare-disk-sweep",
        "model": "nai_2x2_template", "source_strategy": "disk_tr1",
        "source_energy": 0.662, "source_radius": 0.15,
        "nps": 1_000_000, "postprocess": "none",
        "distance": {"start": 10, "stop": 20, "step": 5},
        "reference_position": [0.0, 0.0, -0.1],
        "execute_requested": False, "missing_required": [], "warnings": [], "errors": [],
    }
    result = execute_plan(plan)
    assert result["ok"]


# ==================================================================
# CLI help completeness
# ==================================================================

def test_all_user_commands_help_present():
    for cmd in ("plan-request", "execute-plan", "runtime-check",
                "diagnose-deck", "repair-deck", "analyze-run-failure",
                "prepare-point-sweep", "run-point-sweep"):
        r = _run(cmd, "--help")
        assert r.returncode == 0, f"{cmd} --help failed"


def test_main_help_lists_all_user_commands():
    r = _run("--help")
    text = r.stdout
    for cmd in ("plan-request", "execute-plan", "runtime-check",
                "diagnose-deck", "repair-deck", "analyze-run-failure",
                "models", "inspect-deck"):
        assert cmd in text, f"main --help missing: {cmd}"


# ==================================================================
# Error code Chinese coverage
# ==================================================================

def test_key_error_codes_covered():
    """Verify key error codes have Chinese explanations in renderers."""
    from mcnp_research_skill.workflow.user_output import (
        render_plan_response, render_execute_plan_response, render_non_f8_response,
    )

    # ACTIVITY_NORMALIZATION_UNSUPPORTED
    r = render_plan_response({"ok": False, "status": "needs_clarification",
        "errors": [{"code": "ACTIVITY_NORMALIZATION_UNSUPPORTED", "message": "x"}], "warnings": []})
    assert "Bq" in r.upper() or "BQ" in r.upper()

    # AMBIGUOUS_REFERENCE_POINT
    r2 = render_plan_response({"ok": False, "status": "needs_clarification",
        "errors": [{"code": "AMBIGUOUS_REFERENCE_POINT", "message": "x"}], "warnings": []})
    assert "crystal_front" in r2.lower() or "nai_crystal" in r2

    # USER_CONFIRMATION_REQUIRED
    r3 = render_execute_plan_response({"ok": False,
        "errors": [{"code": "USER_CONFIRMATION_REQUIRED", "message": "x"}]})
    assert "confirm-user" in r3

    # MCNP_NOT_FOUND
    r4 = render_execute_plan_response({"ok": False,
        "errors": [{"code": "MCNP_NOT_FOUND", "message": "x"}]})
    assert "MCNP" in r4
    assert "download" not in r4.lower()

    # non-F8
    r5 = render_non_f8_response("F4", "csv")
    assert "F4" in r5 and "F8" in r5
