"""End-to-end user scenario acceptance tests.

Uses English natural language to avoid CJK source-file encoding issues.
All scenarios use dry-run or mocked runtime — no real MCNP/MPI execution.
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
        CLI + list(args), cwd=str(Path.cwd()),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _plan(text, **kw):
    args = ["--json", "plan-request", "--text", text]
    for k, v in kw.items():
        args.extend([f"--{k.replace('_', '-')}", str(v)])
    return _run(*args)


def _exec(plan_file, **kw):
    args = ["--json", "execute-plan", "--plan-file", plan_file]
    for k, v in kw.items():
        f = f"--{k.replace('_', '-')}"
        if v is True:
            args.append(f)
        elif v is not False:
            args.extend([f, str(v)])
    return _run(*args)


# ==================================================================
# S1: 3x3 verified, crystal front sweep, CSV only
# ==================================================================

def test_s1_3x3_crystal_front_csv(tmp_path):
    text = "3 inch NaI, distance from nai crystal front surface 10 to 20 cm step 5 cm, nps 1e6, Cs-137, csv only"
    r = _plan(text)
    assert r.returncode == 0, r.stdout[:200]
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["model"] == "nai_3x3_verified"
    assert p["model_verified"] is True
    assert p["canonical_reference_point"] == "nai_crystal_front_surface"
    assert p["nps"] == 1_000_000
    assert p["postprocess"] == "csv"
    assert p["source_strategy"] == "point_sdef_pos"
    assert p["status"] == "ready_for_review"

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")
    r2 = _exec(str(plan_file))
    assert r2.returncode == 0
    p2 = json.loads(r2.stdout)
    assert p2["ok"]
    assert p2["dry_run"] is True
    assert p2["workflow_result"]["prepared_count"] == 3


# ==================================================================
# S2: 2x2 template, aluminum shell, execute requested, CSV
# ==================================================================

def test_s2_2x2_aluminum_shell():
    text = "2 inch NaI, nps 1e7, distance from aluminum shell 10 to 20 cm step 5 cm, execute and csv"
    r = _plan(text)
    p = json.loads(r.stdout)
    assert p["model"] == "nai_2x2_template"
    assert p["model_verified"] is False
    assert p["requires_user_validation"] is True
    assert p["canonical_reference_point"] == "aluminum_shell_front"
    assert p["reference_point_verified"] is False
    assert p["nps"] == 10_000_000
    assert p["postprocess"] == "csv"
    assert p["execute_requested"] is True
    assert "source_energy" in p["missing_required"]
    assert "human_summary" in p
    assert "2x2" in p["human_summary"] or "未验证" in p["human_summary"]


# ==================================================================
# S3: 2x2 + Cs-137, confirm + mock execute
# ==================================================================

def test_s3_2x2_cs137_confirm_mock_execute(tmp_path):
    text = "2 inch NaI, Cs-137 point source, distance from aluminum shell 10 to 20 cm step 5 cm, nps 1e7, csv only, execute"
    r = _plan(text)
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["source_energy"] == 0.662
    assert p["missing_required"] == []

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")

    # Without --confirm-user
    r2 = _exec(str(plan_file), execute=True)
    p2 = json.loads(r2.stdout)
    assert any(e["code"] == "USER_CONFIRMATION_REQUIRED" for e in p2.get("errors", []) if isinstance(e, dict))

    # Mocked execute with cpu=8
    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ), mock.patch("os.cpu_count", return_value=8):
        from mcnp_research_skill.workflow.execute_plan import execute_plan
        result = execute_plan(p, execute=True, confirm_user=True)
        assert "-np 9" in (result.get("command_preview") or "")


# ==================================================================
# S4: 1x1 template, crystal center sweep
# ==================================================================

def test_s4_1x1_crystal_center(tmp_path):
    text = "1 inch NaI, point source, distances 5 10 15 cm from crystal center, Cs-137, nps 1e6, prepare only"
    r = _plan(text)
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["model"] == "nai_1x1_template"
    assert p["canonical_reference_point"] == "nai_crystal_center"
    assert p["source_energy"] == 0.662
    assert p["execute_requested"] is False

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")
    r2 = _exec(str(plan_file))
    assert r2.returncode == 0
    p2 = json.loads(r2.stdout)
    wf = p2["workflow_result"]
    for item in wf.get("items", []):
        d = item["distance"]
        assert item["source_position"][2] == pytest.approx(1.27 + d)


# ==================================================================
# S5: Ambiguous crystal surface
# ==================================================================

def test_s5_ambiguous_crystal_surface():
    text = "3 inch NaI, distance from crystal surface 10 cm, nps 1e6"
    r = _plan(text)
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert any(e["code"] == "AMBIGUOUS_REFERENCE_POINT" for e in p.get("errors", []) if isinstance(e, dict))
    assert p["status"] in ("needs_clarification", "blocked")


# ==================================================================
# S6: Batch run existing deck, no CSV, no plot
# ==================================================================

def test_s6_batch_run_no_csv():
    text = "batch run existing txt files, no csv extraction, no plot"
    r = _plan(text)
    p = json.loads(r.stdout)
    assert p["intent"] == "batch_run_only"
    assert p["postprocess"] == "none"


# ==================================================================
# S7: Preserve existing source, only change NPS
# ==================================================================

def test_s7_preserve_source_change_nps():
    text = "preserve existing source in my deck, nps 1e7, then batch run"
    r = _plan(text)
    p = json.loads(r.stdout)
    assert p["source_strategy"] == "preserve_existing_source"
    assert p["nps"] == 10_000_000
    assert p["intent"] in ("batch_run_only", "run_only")


# ==================================================================
# S8: Non-F8 tally requesting CSV → blocked
# ==================================================================

def test_s8_f4_csv_blocked(tmp_path):
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\n\nmode p\nf4:p 1\nnps 100\n"
    (tmp_path / "f4_deck.txt").write_text(deck, encoding="utf-8")

    from mcnp_research_skill.workflow.planner import plan_workflow
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file

    inspection = inspect_deck_file(str(tmp_path / "f4_deck.txt"))
    plan = plan_workflow(inspection, workflow_mode="run-only",
                         source_strategy="preserve_existing_source",
                         postprocess="csv")
    assert any(b["code"] == "CSV_REQUIRES_F8" for b in plan.get("blocked", []))

    plan2 = plan_workflow(inspection, workflow_mode="run-only",
                          source_strategy="preserve_existing_source",
                          postprocess="none")
    assert not plan2.get("blocked")


# ==================================================================
# S9: Diagnose deck for MCNP5 compatibility
# ==================================================================

def test_s9_diagnose_deck(tmp_path):
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\n" + ("x" * 85) + "\nnps 100\n"
    (tmp_path / "bad.txt").write_text(deck, encoding="utf-8")

    text = "diagnose this deck for MCNP5_RSICC 1.14 compatibility"
    r = _plan(text)
    p = json.loads(r.stdout)
    assert p["intent"] == "diagnose_deck"

    r2 = _run("--json", "diagnose-deck", "--input", str(tmp_path / "bad.txt"), "--mcnp-version", "mcnp5_rsicc_1_14")
    p2 = json.loads(r2.stdout)
    assert any(i["code"] in ("TAB_CHARACTER", "LINE_TOO_LONG") for i in p2["issues"])
    for iss in p2["issues"]:
        assert "ai_guidance" in iss


# ==================================================================
# S10: Activity Bq != NPS
# ==================================================================

def test_s10_activity_bq_not_nps():
    text = "2 inch NaI, Cs-137 activity 1e6 Bq, distance from crystal front 10 cm, run csv"
    r = _plan(text)
    p = json.loads(r.stdout)
    errs = p.get("errors", [])
    assert any(e["code"] == "ACTIVITY_NORMALIZATION_UNSUPPORTED" for e in errs)
    # nps should NOT be set from activity value 1e6 Bq
    # (nps may still be None or caught by activity error)
    assert p.get("nps") is None or p["nps"] != 1_000_000


# ==================================================================
# S11: Disk source missing radius
# ==================================================================

def test_s11_disk_missing_radius():
    text = "2 inch NaI, disk source, distance from aluminum shell 10 to 20 cm step 5 cm, Cs-137, nps 1e7"
    r = _plan(text)
    p = json.loads(r.stdout)
    assert p["source_strategy"] == "disk_tr1"
    assert "source_radius" in p["missing_required"]


# ==================================================================
# S12: Disk source with radius
# ==================================================================

def test_s12_disk_with_radius(tmp_path):
    text = "2 inch NaI, disk source, radius 0.15 cm, distance from aluminum shell 10 to 20 cm step 5 cm, Cs-137, nps 1e7, csv only"
    r = _plan(text)
    p = json.loads(r.stdout)
    assert p["source_strategy"] == "disk_tr1"
    assert p["source_radius"] == 0.15
    assert p["source_energy"] == 0.662

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(p), encoding="utf-8")
    r2 = _exec(str(plan_file))
    assert r2.returncode == 0
    p2 = json.loads(r2.stdout)
    assert p2["ok"]


# ==================================================================
# S13: Runtime missing MCNP
# ==================================================================

def test_s13_runtime_missing_mcnp(tmp_path):
    text = "2 inch NaI, Cs-137 point source, distance from aluminum shell 10 cm, nps 1e6, execute"
    r = _plan(text)
    p = json.loads(r.stdout)

    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": False, "command": None, "path": None, "source": None},
    ):
        from mcnp_research_skill.workflow.execute_plan import execute_plan
        result = execute_plan(p, execute=True, confirm_user=True)
        assert not result["ok"]
        assert any(e["code"] == "MCNP_NOT_FOUND" for e in result["errors"])


# ==================================================================
# S14: Runtime missing MPI launcher
# ==================================================================

def test_s14_runtime_missing_mpi(tmp_path):
    text = "2 inch NaI, Cs-137 point source, distance from aluminum shell 10 cm, nps 1e6, execute"
    r = _plan(text)
    p = json.loads(r.stdout)

    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": False, "command": None, "path": None, "source": None},
    ):
        from mcnp_research_skill.workflow.execute_plan import execute_plan
        result = execute_plan(p, execute=True, confirm_user=True)
        assert not result["ok"]
        assert any(e["code"] == "MPI_LAUNCHER_NOT_FOUND" for e in result["errors"])


# ==================================================================
# S15: np recommendation logic
# ==================================================================

def test_s15_cpu_16_np_17():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    with mock.patch("os.cpu_count", return_value=16):
        result = run_runtime_check()
        assert result["recommended_np"] == 17
        assert result["np_policy"] == "logical_processors_plus_one"


def test_s15_cpu_8_np_9():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    with mock.patch("os.cpu_count", return_value=8):
        result = run_runtime_check()
        assert result["recommended_np"] == 9


def test_s15_np_override():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    result = run_runtime_check(np=4)
    assert result["recommended_np"] == 4
    assert result["np_policy"] == "user_override"


# ==================================================================
# S16: Plan file workflow
# ==================================================================

def test_s16_plan_file_workflow(tmp_path):
    text = "2 inch NaI, distance 10 cm from crystal front, Cs-137, nps 1e6, prepare only"

    plan_file = tmp_path / "plan.json"
    r1 = _plan(text, output=str(plan_file))
    assert r1.returncode == 0
    assert plan_file.exists()

    # dry-run
    r2 = _exec(str(plan_file))
    assert r2.returncode == 0
    p2 = json.loads(r2.stdout)
    assert p2["ok"]
    assert p2["dry_run"] is True

    # no confirm
    r3 = _exec(str(plan_file), execute=True)
    p3 = json.loads(r3.stdout)
    assert any(e["code"] == "USER_CONFIRMATION_REQUIRED" for e in p3.get("errors", []) if isinstance(e, dict))

    # mocked execute + confirm
    with mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mpi_launcher",
        return_value={"found": True, "command": "mpirun", "path": "/usr/bin/mpirun", "source": "PATH"},
    ), mock.patch(
        "mcnp_research_skill.mcnp_run.runtime._find_mcnp_exe",
        return_value={"found": True, "command": "mcnp5mpi", "path": "/opt/mcnp/mcnp5mpi", "source": "PATH"},
    ), mock.patch("os.cpu_count", return_value=8):
        r4 = _exec(str(plan_file), execute=True, confirm_user=True)
        p4 = json.loads(r4.stdout)
        assert p4["command_preview"] is not None


# ==================================================================
# Cross-scenario assertions
# ==================================================================

def test_all_plans_have_human_summary():
    texts = [
        "3 inch NaI, distance 10 cm from crystal front, Cs-137, nps 1e6",
        "2 inch NaI, distance 10 cm from aluminum shell, Cs-137, nps 1e6",
    ]
    for text in texts:
        r = _plan(text)
        p = json.loads(r.stdout)
        if p.get("ok"):
            assert "human_summary" in p, f"Missing human_summary: {text}"
            assert "confirmation_prompt" in p, f"Missing confirmation_prompt: {text}"
            assert "cli_preview" in p, f"Missing cli_preview: {text}"
