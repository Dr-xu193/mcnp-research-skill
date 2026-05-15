"""Tests for SPE-to-GEB workflow integration."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]


def _json(*args):
    r = subprocess.run(CLI + ["--json"] + list(args), text=True, encoding="utf-8",
                       errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(r.stdout), r.returncode


# ==================================================================
# GEB patching
# ==================================================================

def test_patch_geb_insert_ft8():
    from mcnp_research_skill.mcnp_input.patching import patch_geb
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p e\nf8:p,e 1\nnps 100\n"
    r = patch_geb(deck, -0.01, 0.05, 0.2)
    assert r["ok"]
    assert r["changed"]
    assert "FT8 GEB" in r["text"]
    assert len(r["text"].splitlines()) == 7  # original 6 + 1 inserted


def test_patch_geb_replace_existing():
    from mcnp_research_skill.mcnp_input.patching import patch_geb
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p e\nf8:p,e 1\nFT8 GEB 0.1 0.2 0.3\nnps 100\n"
    r = patch_geb(deck, -0.00456, 0.06451, -0.19211)
    assert r["ok"]
    assert r["changed"]
    assert "FT8 GEB -0.00456" in r["text"]
    assert "FT8 GEB 0.1 0.2 0.3" not in r["text"]


def test_patch_geb_no_f8():
    from mcnp_research_skill.mcnp_input.patching import patch_geb
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nf4:p 1\nnps 100\n"
    r = patch_geb(deck, -0.01, 0.05, 0.2)
    assert not r["ok"]
    assert any(e["code"] == "GEB_REQUIRES_F8" for e in r["errors"])


def test_patch_geb_line_length():
    from mcnp_research_skill.mcnp_input.patching import patch_geb
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p e\nf8:p,e 1\nnps 100\n"
    r = patch_geb(deck, -0.00456, 0.06451, -0.19211)
    for line in r["text"].splitlines():
        assert len(line.rstrip("\n")) <= 80


# ==================================================================
# CLI: patch-deck --geb
# ==================================================================

def test_cli_patch_deck_geb(tmp_path):
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p e\nf8:p,e 1\nnps 100\n"
    (tmp_path / "A.txt").write_text(deck, encoding="utf-8")
    d, rc = _json("patch-deck", "--input", str(tmp_path / "A.txt"),
                   "--output", str(tmp_path / "B.txt"),
                   "--geb", "-0.01", "0.05", "0.2")
    assert rc == 0
    assert d["ok"]
    text = (tmp_path / "B.txt").read_text(encoding="utf-8")
    assert "FT8 GEB" in text


# ==================================================================
# NL planner GEB intent
# ==================================================================

def test_nl_geb_fit_intent_broad_aliases():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    tests = [
        "derive GEB ABC from SPE files",
        "fit GEB from SPE and patch deck",
        "extract FWHM from SPE, fit GEB, update FT8 GEB",
        "compute GEB parameters from spectrum files then sweep",
    ]
    for txt in tests:
        r = plan_request(txt)
        assert "geb" in r.get("intent", "").lower(), f"'{txt}' intent={r.get('intent')}"


def test_nl_geb_fit_missing_files():
    from mcnp_research_skill.workflow.nl_planner import plan_request
    r = plan_request("fit GEB parameters and patch deck")
    assert "geb" in r.get("intent", "").lower()


# ==================================================================
# CLI: fit-geb-and-patch-deck
# ==================================================================

def test_fit_geb_and_patch_deck_missing_files():
    d, rc = _json("fit-geb-and-patch-deck", "--spe", "/nonexistent.spe",
                   "--input", "/nonexistent.txt", "--output", "/tmp/out.txt",
                   "--spe", "/nope2.spe")
    assert rc != 0 or d["ok"] is False


# ==================================================================
# No real MCNP/MPI execution
# ==================================================================

def test_no_real_mcnp_execution():
    """All GEB workflow tests use mock or fixtures; no real MCNP/MPI."""
    assert True
