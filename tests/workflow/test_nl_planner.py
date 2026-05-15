"""Tests for natural-language workflow planner."""
from __future__ import annotations

import json
import re
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


# wrap CJK in a helper to avoid source-file encoding issues
def _cjk(*codepoints):
    return "".join(chr(cp) for cp in codepoints)


# ==================================================================
# model detection
# ==================================================================

def test_plan_2x2_aluminum_shell():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "2 inch NaI, 1e7 histories, distance from aluminum shell front 10 to 20 cm step 5 cm, execute and output CSV"
    result = plan_request(text)
    assert result["model"] == "nai_2x2_template"
    assert result["model_verified"] is False
    assert result["requires_user_validation"] is True
    assert result["canonical_reference_point"] == "aluminum_shell_front"
    assert result["distance"]["start"] == 10
    assert result["distance"]["stop"] == 20
    assert result["distance"]["step"] == 5
    assert result["nps"] == 10_000_000
    assert result["postprocess"] == "csv"
    assert result["execute_requested"] is True


def test_plan_3x3_crystal_front():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "3 inch NaI, distance from crystal front surface 10 to 20 cm step 5 cm, nps 1e6, csv only, Cs-137 source"
    result = plan_request(text)
    assert result["model"] == "nai_3x3_verified"
    assert result["model_verified"] is True
    assert result["canonical_reference_point"] == "nai_crystal_front_surface"
    assert result["nps"] == 1_000_000
    assert result["source_energy"] == 0.662
    assert result["postprocess"] == "csv"
    assert result["status"] == "ready_for_review"


def test_plan_ambiguous_crystal_surface():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "2 inch NaI, distance from crystal surface 10 cm, Cs-137, nps 1e6"
    result = plan_request(text)
    assert any(e["code"] == "AMBIGUOUS_REFERENCE_POINT" for e in result.get("errors", []))


def test_activity_bq_unsupported():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "2 inch NaI, activity 1e6 Bq, distance 10 cm from aluminum shell front"
    result = plan_request(text)
    errors = result.get("errors", [])
    assert any(e["code"] == "ACTIVITY_NORMALIZATION_UNSUPPORTED" for e in errors)


def test_plan_3inch_verified_alias():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    for alias in ("3 inch NaI", "3\" NaI", "3x3 NaI"):
        result = plan_request(f"{alias}, distance 10 cm from aluminum shell, Cs-137, 1e6 nps")
        assert result["model"] == "nai_3x3_verified", f"alias '{alias}' failed"


def test_plan_2inch_template_alias():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    for alias in ("2 inch NaI", "2\" NaI", "2x2 NaI"):
        result = plan_request(f"{alias}, distance 10 cm from aluminum shell, Cs-137, 1e6 nps")
        assert result["model"] == "nai_2x2_template", f"alias '{alias}' failed"


def test_plan_1inch_template_alias():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    for alias in ("1 inch NaI", "1\" NaI", "1x1 NaI"):
        result = plan_request(f"{alias}, distance 10 cm from aluminum shell, Cs-137, 1e6 nps")
        assert result["model"] == "nai_1x1_template", f"alias '{alias}' failed"


# ==================================================================
# source type / energy
# ==================================================================

def test_disk_source_missing_radius():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "2 inch NaI, disk source, distance 10 cm from aluminum shell"
    result = plan_request(text)
    assert result["source_strategy"] == "disk_tr1"
    assert "source_radius" in result["missing_required"]


def test_point_source_assumed():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "2 inch NaI, distance 10 to 20 cm step 5 cm, Cs-137, nps 1e6"
    result = plan_request(text)
    assert result["source_strategy"] == "point_sdef_pos"
    assert any(w["code"] == "SOURCE_STRATEGY_ASSUMED_POINT" for w in result["warnings"])


def test_cs137_energy():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    for text in ("Cs-137", "cs-137", "cesium source"):
        result = plan_request(f"2 inch NaI, distance 10 cm, {text}, nps 1e6")
        assert result["source_energy"] == 0.662, f"'{text}' failed"


def test_kev_energy():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    result = plan_request("2 inch NaI, 662 keV, distance 10 cm, nps 1e6")
    assert result["source_energy"] == 0.662


def test_mev_energy():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    result = plan_request("2 inch NaI, 0.662 MeV, distance 10 cm, nps 1e6")
    assert result["source_energy"] == 0.662


# ==================================================================
# postprocess / intent
# ==================================================================

def test_csv_only():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    result = plan_request("2 inch NaI, csv only no plot, Cs-137, nps 1e6, distance 10 cm")
    assert result["postprocess"] == "csv"


def test_csv_and_plot():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    result = plan_request("2 inch NaI, plot csv, Cs-137, nps 1e6, distance 10 cm")
    assert result["postprocess"] == "csv-and-plot"


def test_no_postprocess():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    result = plan_request("2 inch NaI, run only, no csv, no plot, Cs-137, nps 1e6")
    assert result["postprocess"] == "none"


def test_execute_requested():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    result = plan_request("2 inch NaI, execute and output CSV, Cs-137, nps 1e6, distance 10 cm")
    assert result["execute_requested"] is True


# ==================================================================
# NPS variations
# ==================================================================

def test_nps_scientific():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    for text, expected in (
        ("NPS=1e7", 10_000_000),
        ("nps 1e6", 1_000_000),
        ("histories 1e7", 10_000_000),
        ("nps 1000000", 1_000_000),
    ):
        result = plan_request(f"2 inch NaI, {text}, distance 10 cm, Cs-137")
        assert result["nps"] == expected, f"'{text}' got {result['nps']}"


# ==================================================================
# intent detection
# ==================================================================

def test_intent_diagnose():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "2 inch NaI, diagnose this deck for MCNP5_RSICC 1.14 compatibility"
    result = plan_request(text)
    assert result["intent"] == "diagnose_deck"


def test_intent_batch_run():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    text = "batch run existing txt files, no csv extraction, no plot"
    result = plan_request(text)
    assert result["intent"] == "batch_run_only"
    assert result["postprocess"] == "none"


# ==================================================================
# reference point resolver tests
# ==================================================================

def test_resolve_canonical_names():
    from mcnp_research_skill.models.registry import (
        resolve_reference_point_name,
        get_model_reference_point,
    )
    for name in ("aluminum_shell_front", "nai_crystal_center", "nai_crystal_front_surface"):
        r = resolve_reference_point_name(name)
        assert r["ok"], f"'{name}' should resolve"


def test_resolve_chinese_aliases():
    from mcnp_research_skill.models.registry import resolve_reference_point_name
    pairs = [
        (chr(0x94DD) + chr(0x58F3) + chr(0x8868) + chr(0x9762), "aluminum_shell_front"),  # 铝壳表面
        (chr(0x5916) + chr(0x58F3) + chr(0x8868) + chr(0x9762), "aluminum_shell_front"),  # 外壳表面
        (chr(0x6676) + chr(0x4F53) + chr(0x4E2D) + chr(0x5FC3), "nai_crystal_center"),   # 晶体中心
        (chr(0x6676) + chr(0x4F53) + chr(0x524D) + chr(0x8868) + chr(0x9762), "nai_crystal_front_surface"),  # 晶体前表面
    ]
    for alias, expected in pairs:
        r = resolve_reference_point_name(alias)
        assert r["ok"], f"'{alias}' failed: {r}"
        assert r["canonical_name"] == expected, f"'{alias}' -> {r['canonical_name']}"


def test_ambiguous_aliases_error():
    from mcnp_research_skill.models.registry import resolve_reference_point_name
    for alias in ("crystal_surface", "nai_surface"):
        r = resolve_reference_point_name(alias)
        assert not r["ok"], f"'{alias}' should be ambiguous"
        assert any(e["code"] == "AMBIGUOUS_REFERENCE_POINT" for e in r["errors"])


def test_unknown_reference_point():
    from mcnp_research_skill.models.registry import resolve_reference_point_name
    r = resolve_reference_point_name("bogus_point_xyz")
    assert not r["ok"]
    assert any(e["code"] == "UNKNOWN_REFERENCE_POINT" for e in r["errors"])


def test_get_model_reference_point_3x3():
    from mcnp_research_skill.models.registry import get_model_reference_point
    r = get_model_reference_point("nai_3x3_verified", "nai_crystal_front_surface")
    assert r["ok"]
    assert r["position"] == [0.0, 0.0, 0.0]
    assert r["verified"] is True
    assert "surface_14" in r["basis"]


def test_get_model_reference_point_3x3_center():
    from mcnp_research_skill.models.registry import get_model_reference_point
    r = get_model_reference_point("nai_3x3_verified", "nai_crystal_center")
    assert r["position"] == [0.0, 0.0, 3.81]
    assert r["verified"] is True


def test_get_model_reference_point_3x3_aluminum():
    from mcnp_research_skill.models.registry import get_model_reference_point
    r = get_model_reference_point("nai_3x3_verified", "aluminum_shell_front")
    assert r["position"] == [0.0, 0.0, -0.34]
    assert r["verified"] is True


def test_get_model_reference_point_1x1_center():
    from mcnp_research_skill.models.registry import get_model_reference_point
    r = get_model_reference_point("nai_1x1_template", "nai_crystal_center")
    assert r["position"] == [0.0, 0.0, 1.27]
    assert r["verified"] is False


def test_get_model_reference_point_2x2_aluminum():
    from mcnp_research_skill.models.registry import get_model_reference_point
    r = get_model_reference_point("nai_2x2_template", "aluminum_shell_front")
    assert r["position"] == [0.0, 0.0, -0.1]
    assert r["verified"] is False
    assert r["requires_user_validation"] is True


# ==================================================================
# runtime preflight
# ==================================================================

def test_runtime_check_logical_processors():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    result = run_runtime_check()
    assert result["ok"] is True
    assert result["logical_processors"] > 0
    assert result["recommended_np"] == result["logical_processors"] + 1
    assert result["np_policy"] == "logical_processors_plus_one"
    assert "mpi_launcher" in result
    assert "mcnp_executable" in result
    assert "command_preview" in result


def test_runtime_check_np_override():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    result = run_runtime_check(np=8)
    assert result["recommended_np"] == 8
    assert result["np_policy"] == "user_override"


def test_runtime_check_mock_cpu_count_16():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    with mock.patch("os.cpu_count", return_value=16):
        result = run_runtime_check()
        assert result["logical_processors"] == 16
        assert result["recommended_np"] == 17


def test_runtime_check_mock_cpu_count_8():
    from mcnp_research_skill.mcnp_run.runtime import run_runtime_check
    with mock.patch("os.cpu_count", return_value=8):
        result = run_runtime_check()
        assert result["recommended_np"] == 9


# ==================================================================
# sweep --builtin-model + --reference-point CLI
# ==================================================================

def test_prepare_point_sweep_builtin_model(tmp_path):
    r = _run("prepare-point-sweep", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"), "--distances", "10",
             "--axis", "z", "--direction", "1",
             "--reference-point", "crystal_front",
             "--source-energy", "0.662", "--nps", "1e6")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["prepared_count"] == 1


def test_prepare_disk_sweep_builtin_model(tmp_path):
    r = _run("prepare-disk-sweep", "--builtin-model", "nai_2x2_template",
             "--work-dir", str(tmp_path / "w"), "--distances", "15",
             "--axis", "z", "--direction", "1",
             "--reference-point", "aluminum_shell_front",
             "--source-energy", "0.662", "--source-radius", "0.15", "--nps", "1e6")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]


def test_prepare_point_sweep_reference_point_3x3_front(tmp_path):
    r = _run("prepare-point-sweep", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"), "--distances", "10",
             "--axis", "z", "--direction", "1",
             "--reference-point", "nai_crystal_front_surface",
             "--source-energy", "0.662", "--nps", "1e6")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["items"][0]["source_position"] == [0.0, 0.0, 10.0]


def test_prepare_point_sweep_reference_point_2x2_aluminum(tmp_path):
    r = _run("prepare-point-sweep", "--builtin-model", "nai_2x2_template",
             "--work-dir", str(tmp_path / "w"), "--distances", "10",
             "--axis", "z", "--direction", "1",
             "--reference-point", "aluminum_shell_front",
             "--source-energy", "0.662", "--nps", "1e6")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    pos = p["items"][0]["source_position"]
    assert pos[2] == pytest.approx(9.9)


def test_prepare_point_sweep_reference_point_1x1_center(tmp_path):
    r = _run("prepare-point-sweep", "--builtin-model", "nai_1x1_template",
             "--work-dir", str(tmp_path / "w"), "--distances", "10",
             "--axis", "z", "--direction", "1",
             "--reference-point", "crystal_center",
             "--source-energy", "0.662", "--nps", "1e6")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    pos = p["items"][0]["source_position"]
    assert pos[2] == pytest.approx(11.27)


# ==================================================================
# error cases
# ==================================================================

def test_input_and_builtin_conflict(tmp_path):
    (tmp_path / "A.txt").write_text("mode p\nnps 100\n", encoding="utf-8")
    r = _run("prepare-point-sweep", "--input", str(tmp_path / "A.txt"),
             "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"), "--distances", "10",
             "--source-energy", "0.662", "--nps", "1e6")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert any(e["code"] == "INPUT_CONFLICT" for e in p.get("errors", []) if isinstance(e, dict))


def test_unknown_reference_point_sweep(tmp_path):
    r = _run("prepare-point-sweep", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"), "--distances", "10",
             "--reference-point", "nonexistent_point_xyz",
             "--source-energy", "0.662", "--nps", "1e6")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert any(
        e["code"] in ("UNKNOWN_REFERENCE_POINT",)
        for e in p.get("errors", []) if isinstance(e, dict)
    )


def test_model_not_detected():
    r = _run("plan-request", "--text", "run a disk source simulation")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert p["status"] == "needs_clarification"


# ==================================================================
# CLI: plan-request and runtime-check
# ==================================================================

def test_cli_plan_request_json():
    r = _run("plan-request", "--text",
             "2 inch NaI, distance 10 to 20 cm step 5 from aluminum shell, Cs-137, nps 1e6")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["model"] == "nai_2x2_template"
    assert "human_summary" in p
    assert "confirmation_prompt" in p
    assert "cli_preview" in p
    assert "runtime_preflight" in p


def test_cli_runtime_check():
    r = _run("runtime-check")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert "logical_processors" in p
    assert "recommended_np" in p
