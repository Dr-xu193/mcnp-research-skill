"""Tests for confirmation-safe execute-plan."""
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
        CLI + list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _make_plan(**overrides):
    """Build a minimal valid plan dict."""
    base = {
        "ok": True,
        "status": "ready_for_review",
        "intent": "prepare_sweep",
        "workflow_command": "prepare-point-sweep",
        "model": "nai_2x2_template",
        "model_verified": False,
        "source_strategy": "point_sdef_pos",
        "source_energy": 0.662,
        "nps": 1_000_000,
        "postprocess": "csv",
        "reference_point": "aluminum shell",
        "canonical_reference_point": "aluminum_shell_front",
        "reference_position": [0.0, 0.0, -0.1],
        "distance": {"start": 10, "stop": 20, "step": 5, "distances": None, "unit": "cm"},
        "execute_requested": False,
        "missing_required": [],
        "warnings": [],
        "errors": [],
    }
    base.update(overrides)
    return base


# ==================================================================
# dry-run: sweep works
# ==================================================================

def test_execute_plan_dry_run_2x2_aluminum(tmp_path):
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan()
    result = execute_plan(plan)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["executed"] is False
    wf = result["workflow_result"]
    assert wf["prepared_count"] == 3


def test_execute_plan_dry_run_3x3_crystal_front(tmp_path):
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(
        model="nai_3x3_verified",
        model_verified=True,
        reference_point="crystal front",
        canonical_reference_point="nai_crystal_front_surface",
        reference_position=[0.0, 0.0, 0.0],
        requires_user_validation=False,
        requires_user_validation_rp=False,
    )
    result = execute_plan(plan)
    assert result["ok"] is True
    assert result["dry_run"] is True


# ==================================================================
# confirmation gate
# ==================================================================

def test_execute_without_confirm_user():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(execute_requested=True)
    result = execute_plan(plan, execute=True, confirm_user=False)
    assert result["ok"] is False
    assert any(e["code"] == "USER_CONFIRMATION_REQUIRED" for e in result["errors"])


# ==================================================================
# plan validation
# ==================================================================

def test_plan_not_executable_status():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(status="blocked", errors=[{"code": "TEST", "message": "x"}])
    result = execute_plan(plan)
    assert result["ok"] is False
    assert any(e["code"] == "PLAN_NOT_EXECUTABLE" for e in result["errors"])


def test_plan_missing_required():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(missing_required=["source_energy"], source_energy=None)
    result = execute_plan(plan)
    assert result["ok"] is False
    assert any(e["code"] == "PLAN_MISSING_REQUIRED" for e in result["errors"])


def test_plan_invalid_json():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    result = execute_plan("not a dict")  # type: ignore
    assert result["ok"] is False
    assert any(e["code"] == "PLAN_FILE_INVALID" for e in result["errors"])


def test_ambiguous_ref_plan_not_executable():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(
        status="needs_clarification",
        errors=[{"code": "AMBIGUOUS_REFERENCE_POINT", "message": "..."}],
    )
    result = execute_plan(plan)
    assert any(e["code"] == "PLAN_NOT_EXECUTABLE" for e in result["errors"])


# ==================================================================
# runtime gates (mock)
# ==================================================================

def test_execute_mcnp_not_found():
    from mcnp_research_skill.workflow.execute_plan import execute_plan
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check

    plan = _make_plan(execute_requested=True)
    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": False, "command": "mcnp5mpi", "path": None, "source": None},
    ):
        result = execute_plan(plan, execute=True, confirm_user=True)
        assert result["ok"] is False
        assert any(e["code"] == "MCNP_NOT_FOUND" for e in result["errors"])


def test_execute_mpi_not_found():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(execute_requested=True)
    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": False, "command": "mpirun", "path": None, "source": None},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ):
        result = execute_plan(plan, execute=True, confirm_user=True)
        assert result["ok"] is False
        assert any(e["code"] == "MPI_LAUNCHER_NOT_FOUND" for e in result["errors"])


def test_execute_all_found_mock_runner():
    """When all found + confirmed, execute should be attempted (runner will fail without real MCNP, but gates pass)."""
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(execute_requested=True)
    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ), mock.patch("os.cpu_count", return_value=8):
        result = execute_plan(plan, execute=True, confirm_user=True)
        # Gates pass, but actual runner fails (no real MCNP) — that's OK for this test
        # Either ok=False from runner or ok=True; runner error is fine
        assert not any(
            e["code"] in ("MCNP_NOT_FOUND", "MPI_LAUNCHER_NOT_FOUND", "USER_CONFIRMATION_REQUIRED")
            for e in result["errors"]
        )


# ==================================================================
# np / command overrides
# ==================================================================

def test_np_override():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan()
    with mock.patch("os.cpu_count", return_value=16):
        result = execute_plan(plan, np=4)
        rt = result["runtime_preflight"]
        assert rt["recommended_np"] == 4
        assert rt["np_policy"] == "user_override"


def test_mpi_command_override():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan()
    result = execute_plan(plan, mpi_command="mpirun -np 6 mcnp5mpi.exe")
    assert result["command_preview"] == "mpirun -np 6 mcnp5mpi.exe"


def test_mcnp_exe_override_with_not_found():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(execute_requested=True)
    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ):
        result = execute_plan(plan, execute=True, confirm_user=True, mcnp_exe="/custom/mcnp5mpi")
        # mcnp_exe override should be accepted even if not found
        # (user explicitly provided it, may be correct)
        assert not any(e["code"] == "MCNP_NOT_FOUND" for e in result["errors"])


# ==================================================================
# disk source plan
# ==================================================================

def test_disk_source_dry_run():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(
        source_strategy="disk_tr1",
        source_radius=0.15,
        workflow_command="prepare-disk-sweep",
    )
    result = execute_plan(plan)
    assert result["ok"] is True


# ==================================================================
# unsupported command
# ==================================================================

def test_unsupported_command():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(workflow_command="unknown_command", intent="unknown")
    result = execute_plan(plan)
    assert result["ok"] is False
    assert any(e["code"] == "PLAN_COMMAND_UNSUPPORTED" for e in result["errors"])


# ==================================================================
# diagnose plan
# ==================================================================

def test_diagnose_plan_executes():
    from mcnp_research_skill.workflow.execute_plan import execute_plan

    plan = _make_plan(
        workflow_command="diagnose-deck",
        intent="diagnose_deck",
    )
    result = execute_plan(plan)
    assert result["ok"] is True


# ==================================================================
# CLI tests
# ==================================================================

def test_cli_plan_request_with_output(tmp_path):
    r = _run("plan-request", "--text",
             "2 inch NaI, distance 10 to 20 cm step 5 from aluminum shell, Cs-137, nps 1e6",
             "--output", str(tmp_path / "plan.json"))
    assert r.returncode == 0
    assert (tmp_path / "plan.json").exists()


def test_cli_execute_plan_dry_run(tmp_path):
    # Create plan first
    _run("plan-request", "--text",
         "2 inch NaI, distance 10 to 20 cm step 5 from aluminum shell, Cs-137, nps 1e6",
         "--output", str(tmp_path / "plan.json"))
    r = _run("execute-plan", "--plan-file", str(tmp_path / "plan.json"))
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["dry_run"] is True


def test_cli_execute_plan_missing_file():
    r = _run("execute-plan", "--plan-file", "/tmp/nonexistent_plan.json")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert any(e["code"] == "PLAN_FILE_NOT_FOUND" for e in p.get("errors", []) if isinstance(e, dict))


def test_cli_execute_without_confirm(tmp_path):
    _run("plan-request", "--text",
         "2 inch NaI, distance 10 to 20 cm step 5 from aluminum shell, Cs-137, nps 1e6",
         "--output", str(tmp_path / "plan.json"))
    r = _run("execute-plan", "--plan-file", str(tmp_path / "plan.json"), "--execute")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert any(e["code"] == "USER_CONFIRMATION_REQUIRED" for e in p.get("errors", []) if isinstance(e, dict))


def test_cli_execute_plan_invalid_json(tmp_path):
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    r = _run("execute-plan", "--plan-file", str(tmp_path / "bad.json"))
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert any(e["code"] == "PLAN_FILE_INVALID" for e in p.get("errors", []) if isinstance(e, dict))
