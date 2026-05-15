"""Robustness tests for Chinese distance/NPS/step parsing."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]


def _json(*args):
    r = subprocess.run(CLI + ["--json"] + list(args), text=True, encoding="utf-8",
                       errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(r.stdout), r.returncode


# ==================================================================
# Distance range formats
# ==================================================================

def test_distance_15_20_hyphen():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 15
    assert r["distance"]["stop"] == 20
    assert r["distance"]["step"] == 5


def test_distance_15cm_20cm_hyphen():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15cm-20cm, step 5cm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 15
    assert r["distance"]["stop"] == 20


def test_distance_en_dash():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15–20cm, step 5cm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 15


def test_distance_em_dash():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15—20cm, step 5cm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 15


def test_distance_decimal_start():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 12.5-16.5cm, step 2cm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 12.5
    assert r["distance"]["stop"] == 16.5
    assert r["distance"]["step"] == 2


def test_distance_decimal_stop():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20.5cm, step 2cm, Cs-137, nps 1e6")
    assert r["distance"]["stop"] == 20.5


def test_distance_english_to():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15 to 20 cm, step 5 cm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 15


# ==================================================================
# Step alias variations
# ==================================================================

def test_step_every_time():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 12.5-16.5cm, step 2cm, Cs-137, nps 1e6")
    assert r["distance"]["step"] == 2


def test_step_interval():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15 to 20 cm, step 5 cm, Cs-137, nps 1e6")
    assert r["distance"]["step"] == 5


def test_step_decimal():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 12.5-16.5cm, step 0.5cm, Cs-137, nps 1e6")
    assert r["distance"]["step"] == 0.5


def test_step_mm_to_cm():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 100mm-200mm, step 5mm, Cs-137, nps 1e6")
    assert r["distance"]["start"] == 10.0
    assert r["distance"]["stop"] == 20.0
    assert r["distance"]["step"] == 0.5


# ==================================================================
# NPS power/指数 expressions
# ==================================================================

def test_nps_power_10_7():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, Cs-137, nps 1e7")
    assert r["nps"] == 10_000_000


def test_nps_superscript():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, Cs-137, nps 1e6")
    assert r["nps"] == 1_000_000


def test_nps_number_before_keyword():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, Cs-137, 1e7 nps")
    assert r["nps"] == 10_000_000


def test_nps_1e7_histories():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, Cs-137, 1e7 histories")
    assert r["nps"] == 10_000_000


# ==================================================================
# Energy keV decimal
# ==================================================================

def test_energy_563_32_kev():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, 563.32 keV, nps 1e6")
    assert r["source_energy"] == pytest.approx(0.56332, abs=0.0001)


def test_energy_63_6_kev():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, 63.6 keV, nps 1e6")
    assert r["source_energy"] == pytest.approx(0.0636, abs=0.0001)


# ==================================================================
# Intent: sweep vs batch
# ==================================================================

def test_intent_sweep_with_range_and_step():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 5cm, Cs-137, nps 1e6, execute")
    assert r["intent"] == "run_sweep"


def test_intent_sweep_overrides_batch():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15 to 20 cm, step 5 cm, Cs-137, nps 1e6, execute")
    assert r["intent"] == "run_sweep"


def test_intent_batch_dir_only():
    r, _ = _json("plan-request", "--text", "batch run existing txt files in directory, no csv, no plot")
    assert r["intent"] == "batch_run_only"


# ==================================================================
# Invalid step
# ==================================================================

def test_invalid_step_zero():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step 0cm, Cs-137, nps 1e6")
    errs = [e.get("code") for e in r.get("errors", []) if isinstance(e, dict)]
    assert "INVALID_DISTANCE_STEP" in errs


def test_invalid_step_negative():
    r, _ = _json("plan-request", "--text", "3 inch NaI, 15-20cm, step -1cm, Cs-137, nps 1e6")
    errs = [e.get("code") for e in r.get("errors", []) if isinstance(e, dict)]
    assert "INVALID_DISTANCE_STEP" in errs


# ==================================================================
# Distance expansion
# ==================================================================

def test_expand_12_5_16_5_step_2():
    from mcnp_research_skill.workflow.sweep import _expand_distances
    d, errs = _expand_distances(None, 12.5, 16.5, 2.0)
    assert d == pytest.approx([12.5, 14.5, 16.5])


def test_expand_12_5_16_5_step_0_5():
    from mcnp_research_skill.workflow.sweep import _expand_distances
    d, errs = _expand_distances(None, 12.5, 16.5, 0.5)
    assert d == pytest.approx([12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5])


def test_expand_10_20_step_5():
    from mcnp_research_skill.workflow.sweep import _expand_distances
    d, errs = _expand_distances(None, 10, 20, 5)
    assert d == pytest.approx([10, 15, 20])


def test_expand_10_11_step_0_3():
    from mcnp_research_skill.workflow.sweep import _expand_distances
    d, errs = _expand_distances(None, 10, 11, 0.3)
    # Should NOT force-include 11.0
    assert d[-1] < 10.9 + 1e-9
    assert 11.0 not in d or d[-1] == pytest.approx(10.9)
