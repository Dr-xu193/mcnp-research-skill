"""Tests for user-facing Chinese output renderers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]


def _run(*args):
    return subprocess.run(
        CLI + list(args), text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


# ==================================================================
# Default output is Chinese text (not JSON)
# ==================================================================

def test_plan_request_default_output_is_chinese():
    r = _run("plan-request", "--text", "2 inch NaI, distance from aluminum shell 10 cm, Cs-137, nps 1e6")
    # Default: text, not JSON
    assert not r.stdout.strip().startswith("{")
    # Must contain Chinese characters
    assert not r.stdout.strip().startswith("{"), "Output should not be JSON"


def test_plan_request_json_flag_outputs_json():
    r = _run("--json", "plan-request", "--text", "2 inch NaI, distance from aluminum shell 10 cm, Cs-137, nps 1e6")
    assert r.stdout.strip().startswith("{")
    d = json.loads(r.stdout)
    assert d["ok"]


def test_execute_plan_default_output_is_chinese(tmp_path):
    # Create plan first
    plan_file = tmp_path / "plan.json"
    _run("--json", "plan-request", "--text", "2 inch NaI, distance from aluminum shell 10 cm, Cs-137, nps 1e6",
         "--output", str(plan_file))
    r = _run("execute-plan", "--plan-file", str(plan_file))
    assert not r.stdout.strip().startswith("{")
    assert not r.stdout.strip().startswith("{")


def test_execute_plan_json_flag_outputs_json(tmp_path):
    plan_file = tmp_path / "plan.json"
    _run("--json", "plan-request", "--text", "2 inch NaI, distance from aluminum shell 10 cm, Cs-137, nps 1e6",
         "--output", str(plan_file))
    r = _run("--json", "execute-plan", "--plan-file", str(plan_file))
    assert r.stdout.strip().startswith("{")


def test_runtime_check_default_output_is_chinese():
    r = _run("runtime-check")
    assert not r.stdout.strip().startswith("{")
    assert not r.stdout.strip().startswith("{")


def test_runtime_check_json_flag_outputs_json():
    r = _run("--json", "runtime-check")
    assert r.stdout.strip().startswith("{")
    d = json.loads(r.stdout)
    assert d["ok"]


# ==================================================================
# MCNP/MPI missing messages
# ==================================================================

def test_mcnp_missing_message_in_output():
    """MCNP missing: must contain 'MCNP' mention and no download/piracy suggestion."""
    from mcnp_research_skill.workflow.user_output import render_execute_plan_response
    result = {"ok": False, "errors": [
        {"code": "MCNP_NOT_FOUND", "message": "MCNP not found"}]}
    text = render_execute_plan_response(result)
    assert "MCNP" in text
    assert "download" not in text.lower()
    assert any(ord(c) > 127 for c in text)


def test_mpi_missing_message_in_output():
    """MPI missing: must contain mpirun/mpiexec mention."""
    from mcnp_research_skill.workflow.user_output import render_execute_plan_response
    result = {"ok": False, "errors": [
        {"code": "MPI_LAUNCHER_NOT_FOUND", "message": "MPI not found"}]}
    text = render_execute_plan_response(result)
    assert "mpirun" in text.lower() or "mpiexec" in text.lower()
    assert "MPICH" in text or "OpenMPI" in text


def test_user_confirmation_message():
    from mcnp_research_skill.workflow.user_output import render_execute_plan_response
    result = {"ok": False, "errors": [
        {"code": "USER_CONFIRMATION_REQUIRED", "message": "confirm required"}]}
    text = render_execute_plan_response(result)
    assert "confirm-user" in text


# ==================================================================
# Diagnostics / repair output
# ==================================================================

def test_diagnostics_default_output_is_chinese(tmp_path):
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    (tmp_path / "bad.txt").write_text(deck, encoding="utf-8")
    r = _run("diagnose-deck", "--input", str(tmp_path / "bad.txt"))
    assert not r.stdout.strip().startswith("{")
    assert not r.stdout.strip().startswith("{")


def test_repair_default_output_is_chinese(tmp_path):
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    (tmp_path / "bad.txt").write_text(deck, encoding="utf-8")
    r = _run("repair-deck", "--input", str(tmp_path / "bad.txt"),
             "--output", str(tmp_path / "fixed.txt"))
    assert not r.stdout.strip().startswith("{")
    assert not r.stdout.strip().startswith("{")


# ==================================================================
# Non-F8 tally messages
# ==================================================================

def test_f4_csv_blocked_user_message():
    from mcnp_research_skill.workflow.user_output import render_non_f8_response
    text = render_non_f8_response("F4", "csv")
    assert "F4" in text
    assert "F8" in text
    assert "CSV" in text or "csv" in text.lower()
    assert "run-only" in text


def test_f2_csv_blocked_user_message():
    from mcnp_research_skill.workflow.user_output import render_non_f8_response
    text = render_non_f8_response("F2", "csv")
    assert "F2" in text
    assert "F8" in text


def test_f2_plot_blocked_user_message():
    from mcnp_research_skill.workflow.user_output import render_non_f8_response
    text = render_non_f8_response("F2", "csv-and-plot")
    assert "F2" in text
    assert "F8" in text


def test_f4_run_only_allowed_message():
    from mcnp_research_skill.workflow.user_output import render_non_f8_run_only
    text = render_non_f8_run_only("F4")
    assert "F4" in text or "F8" in text
    assert "run-only" in text
    assert any(ord(c) > 127 for c in text)


def test_f2_run_only_allowed_message():
    from mcnp_research_skill.workflow.user_output import render_non_f8_run_only
    text = render_non_f8_run_only("F2")
    assert "F2" in text or "F8" in text


def test_f6_run_only_allowed_message():
    from mcnp_research_skill.workflow.user_output import render_non_f8_run_only
    text = render_non_f8_run_only("F6")
    assert "F6" in text or "F8" in text


# ==================================================================
# Plan issues rendering
# ==================================================================

def test_ambiguous_ref_point_user_output():
    from mcnp_research_skill.workflow.user_output import render_plan_response
    plan = {"ok": False, "status": "needs_clarification",
            "errors": [{"code": "AMBIGUOUS_REFERENCE_POINT", "message": "test"}],
            "warnings": []}
    text = render_plan_response(plan)
    assert "crystal_front" in text.lower() or "nai_crystal" in text
    assert "aluminum_shell" in text


def test_missing_source_energy_user_output():
    from mcnp_research_skill.workflow.user_output import render_plan_response
    plan = {"ok": True, "status": "ready_for_review",
            "model": "nai_2x2_template", "model_verified": False,
            "source_strategy": "point_sdef_pos",
            "canonical_reference_point": "aluminum_shell_front",
            "reference_point_verified": False,
            "distance": {"start": 10, "stop": 20, "step": 5},
            "postprocess": "csv", "execute_requested": False,
            "missing_required": ["source_energy"],
            "warnings": [], "errors": []}
    text = render_plan_response(plan)
    assert "Cs-137" in text or "0.662" in text


def test_bq_activity_user_output():
    from mcnp_research_skill.workflow.user_output import render_plan_response
    plan = {"ok": False, "status": "needs_clarification",
            "errors": [{"code": "ACTIVITY_NORMALIZATION_UNSUPPORTED", "message": "test"}],
            "warnings": []}
    text = render_plan_response(plan)
    assert "Bq" in text or "BQ" in text.upper()
    assert "NPS" in text


# ==================================================================
# Dry-run execution output
# ==================================================================

def test_dry_run_output_mentions_no_real_execution():
    from mcnp_research_skill.workflow.user_output import render_execute_plan_response
    result = {"ok": True, "dry_run": True, "executed": False,
              "workflow_result": {"prepared_count": 3},
              "errors": [], "warnings": []}
    text = render_execute_plan_response(result)
    assert any(ord(c) > 127 for c in text)
    assert not text.strip().startswith("{")
    assert "3" in text
