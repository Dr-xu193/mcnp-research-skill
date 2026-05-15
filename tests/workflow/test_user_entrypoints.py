"""User-entrypoint CLI acceptance tests (help text, defaults, --json)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]


def _run(*args):
    return subprocess.run(
        CLI + list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _help(cmd):
    r = _run(cmd, "--help")
    return r.stdout + r.stderr


# ==================================================================
# Help text: plan-request
# ==================================================================

def test_main_help():
    text = _help("")
    assert "--json" in text  # global flag
    assert "plan-request" in text
    assert "execute-plan" in text


def test_plan_request_help():
    text = _help("plan-request")
    assert "--text" in text
    assert "--text-file" in text
    assert "--np" in text


# ==================================================================
# Help text: execute-plan
# ==================================================================

def test_execute_plan_help():
    text = _help("execute-plan")
    assert "--confirm-user" in text
    assert "--execute" in text
    assert "--np" in text
    assert "--mpi-launcher" in text
    assert "--mcnp-exe" in text
    assert "--mpi-command" in text


# ==================================================================
# Help text: runtime-check
# ==================================================================

def test_runtime_check_help():
    text = _help("runtime-check")
    assert "--np" in text
    assert "--mpi-launcher" in text
    assert "--mcnp-exe" in text


# ==================================================================
# Help text: sweep commands
# ==================================================================

def test_sweep_help_has_builtin_model():
    for cmd in ("prepare-point-sweep", "run-point-sweep",
                "prepare-disk-sweep", "run-disk-sweep"):
        text = _help(cmd)
        assert "--builtin-model" in text, f"{cmd} missing --builtin-model"
        assert "--reference-point" in text, f"{cmd} missing --reference-point"
        assert "--reference-position" in text, f"{cmd} missing --reference-position"


# ==================================================================
# Help text: diagnose-deck / repair-deck
# ==================================================================

def test_diagnose_help():
    text = _help("diagnose-deck")
    assert "--builtin-model" in text
    assert "--mcnp-version" in text
    assert "--input" in text


def test_repair_help():
    text = _help("repair-deck")
    assert "--output" in text
    assert "--mcnp-version" in text


# ==================================================================
# Default output is Chinese (not JSON)
# ==================================================================

def test_plan_request_default_chinese():
    r = _run("plan-request", "--text", "3 inch NaI, distance 10 cm, Cs-137, nps 1e6")
    assert not r.stdout.strip().startswith("{")
    assert any(ord(c) > 127 for c in r.stdout)


def test_runtime_check_default_chinese():
    r = _run("runtime-check")
    assert not r.stdout.strip().startswith("{")
    assert any(ord(c) > 127 for c in r.stdout)


def test_diagnose_default_chinese(tmp_path):
    (tmp_path / "A.txt").write_text("test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nnps 100\n", encoding="utf-8")
    r = _run("diagnose-deck", "--input", str(tmp_path / "A.txt"))
    assert not r.stdout.strip().startswith("{")


def test_execute_plan_default_chinese(tmp_path):
    plan_file = tmp_path / "plan.json"
    _run("--json", "plan-request", "--text", "2 inch NaI, distance 10 to 20 cm step 5 cm, Cs-137, nps 1e6",
         "--output", str(plan_file))
    r = _run("execute-plan", "--plan-file", str(plan_file))
    assert not r.stdout.strip().startswith("{")
    # May be "OK" or Chinese text; either is fine (default is text, not JSON)


# ==================================================================
# --json mode still works
# ==================================================================

def test_plan_request_json():
    r = _run("--json", "plan-request", "--text", "3 inch NaI, distance 10 cm, Cs-137, nps 1e6")
    assert r.stdout.strip().startswith("{")
    json.loads(r.stdout)  # must parse


def test_runtime_check_json():
    r = _run("--json", "runtime-check")
    assert r.stdout.strip().startswith("{")
    json.loads(r.stdout)


def test_diagnose_json(tmp_path):
    (tmp_path / "A.txt").write_text("test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nnps 100\n", encoding="utf-8")
    r = _run("--json", "diagnose-deck", "--input", str(tmp_path / "A.txt"))
    assert r.stdout.strip().startswith("{")
    json.loads(r.stdout)


def test_execute_plan_json(tmp_path):
    plan_file = tmp_path / "plan.json"
    _run("--json", "plan-request", "--text", "2 inch NaI, distance 10 cm, Cs-137, nps 1e6",
         "--output", str(plan_file))
    r = _run("--json", "execute-plan", "--plan-file", str(plan_file))
    assert r.stdout.strip().startswith("{")
    json.loads(r.stdout)


# ==================================================================
# Docs smoke check
# ==================================================================

def test_docs_user_scenarios_exists():
    path = Path("docs/user_scenarios.md")
    assert path.exists(), "docs/user_scenarios.md missing"
    text = path.read_text(encoding="utf-8")
    checks = [
        "MCNP5_RSICC", "MPICH", "mpirun", "mpiexec",
        "F8", "F4", "Bq", "aluminum_shell_front",
        "nai_crystal_front_surface", "nai_crystal_center", "--json",
    ]
    for c in checks:
        assert c in text, f"docs/user_scenarios.md missing: {c}"


def test_docs_workflow_cli_exists():
    path = Path("docs/workflow_cli.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    for c in ("plan-request", "execute-plan", "runtime-check", "--builtin-model", "--json"):
        assert c in text, f"docs/workflow_cli.md missing: {c}"


# ==================================================================
# Main --help contains --json
# ==================================================================

def test_main_help_has_json():
    r = _run("--help")
    assert "--json" in r.stdout
    assert "Chinese" in r.stdout or "user-facing" in r.stdout.lower()


# ==================================================================
# Safety gate smoke tests
# ==================================================================

def test_execute_without_confirm_blocked(tmp_path):
    plan_file = tmp_path / "plan.json"
    _run("--json", "plan-request", "--text", "2 inch NaI, distance 10 cm, Cs-137, nps 1e6",
         "--output", str(plan_file))
    r = _run("--json", "execute-plan", "--plan-file", str(plan_file), "--execute")
    p = json.loads(r.stdout)
    assert not p["ok"]
    assert any(e["code"] == "USER_CONFIRMATION_REQUIRED" for e in p.get("errors", []) if isinstance(e, dict))
