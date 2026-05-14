"""Tests for MCNP deck preflight inspection."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.mcnp_input.inspection import inspect_deck, inspect_deck_file

# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------


def deck(*lines: str) -> str:
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# full F8 deck
# ---------------------------------------------------------------------------


FULL_DECK = deck(
    "MCNP test deck",
    "c cell cards",
    "1 0 -1 imp:p=1",
    "2 0 1 imp:p=0",
    "",
    "c surface cards",
    "1 so 100",
    "",
    "mode p e",
    "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662",
    "si1 0 0.15",
    "sp1 -21 1",
    "TR1 0 0 -16.1900",
    "f8:p,e 1",
    "e8 0 1024i 2.5",
    "FT8 GEB -0.00789 0.06769 0.21159",
    "nps 10000000",
)


def test_full_f8_deck_all_present():
    result = inspect_deck(FULL_DECK)
    assert result["ok"] is True

    assert result["nps"]["present"] is True
    assert result["nps"]["value"] == 10000000

    assert result["mode"]["present"] is True
    assert "p" in result["mode"]["particles"]
    assert "e" in result["mode"]["particles"]

    assert result["source"]["has_sdef"] is True
    assert result["source"]["uses_tr"] == ["1"]
    assert result["source"]["has_rad_distribution"] is True
    assert result["source"]["has_si_sp"] is True
    assert len(result["source"]["tr_cards"]) >= 1
    # has rad= + ext= → disk_or_area, NOT point_like
    assert result["source"]["guess"] == "disk_or_area"

    assert len(result["tallies"]) == 1
    t = result["tallies"][0]
    assert t["kind"] == "F8"
    assert t["supported_for_csv"] is True

    assert len(result["energy_cards"]) >= 1

    assert result["geb"]["present"] is True
    assert "GEB" in result["geb"]["raw"]


# ---------------------------------------------------------------------------
# no GEB
# ---------------------------------------------------------------------------


def test_no_geb_does_not_error():
    text = deck("test", "f8:p,e 1", "nps 100")
    result = inspect_deck(text)
    assert result["ok"] is True
    assert result["geb"]["present"] is False


# ---------------------------------------------------------------------------
# F4 deck
# ---------------------------------------------------------------------------


def test_f4_tally_unsupported():
    text = deck("test", "f4:n 1", "nps 100")
    result = inspect_deck(text)
    assert len(result["tallies"]) == 1
    t = result["tallies"][0]
    assert t["kind"] == "F4"
    assert t["supported_for_csv"] is False
    assert any("F4" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# FMESH deck
# ---------------------------------------------------------------------------


def test_fmesh_tally_unsupported():
    text = deck("test", "fmesh4:n geom=xyz origin=0 0 0", "nps 100")
    result = inspect_deck(text)
    assert len(result["tallies"]) == 1
    t = result["tallies"][0]
    assert t["kind"] == "FMESH4"
    assert t["supported_for_csv"] is False


# ---------------------------------------------------------------------------
# no F card
# ---------------------------------------------------------------------------


def test_no_tally_card_errors():
    text = deck("test", "nps 100")
    result = inspect_deck(text)
    assert result["ok"] is False
    assert any(e.get("code") == "NO_TALLY_CARD" for e in result["errors"] if isinstance(e, dict))


# ---------------------------------------------------------------------------
# multiple NPS
# ---------------------------------------------------------------------------


def test_multiple_nps_errors():
    text = deck("test", "nps 100", "c comment", "nps 200", "f8:p,e 1")
    result = inspect_deck(text)
    assert any(e.get("code") == "MULTIPLE_NPS" for e in result["errors"] if isinstance(e, dict))


# ---------------------------------------------------------------------------
# NPS 1e7
# ---------------------------------------------------------------------------


def test_nps_scientific_notation():
    text = deck("test", "nps 1e7", "f8:p,e 1")
    result = inspect_deck(text)
    assert result["nps"]["present"] is True
    assert result["nps"]["value"] == 10000000.0


# ---------------------------------------------------------------------------
# multiple tally types with F8
# ---------------------------------------------------------------------------


def test_mixed_tallies_warns():
    text = deck("test", "f8:p,e 1", "f4:n 2", "nps 100")
    result = inspect_deck(text)
    assert len(result["tallies"]) == 2
    assert result["ok"] is True
    assert any("Multiple tally" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# source_guess
# ---------------------------------------------------------------------------


def test_source_guess_point_like_for_plain_pos():
    text = deck("test", "sdef pos=0 0 0 par=2 erg=0.662", "f8:p,e 1", "nps 100")
    result = inspect_deck(text)
    assert result["source"]["guess"] == "point_like"


def test_source_guess_not_point_like_for_rad_ext():
    text = deck(
        "test",
        "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662",
        "si1 0 0.15",
        "sp1 -21 1",
        "TR1 0 0 -16.1900",
        "f8:p,e 1",
        "nps 100",
    )
    result = inspect_deck(text)
    assert result["source"]["has_rad_distribution"] is True
    assert result["source"]["uses_tr"] == ["1"]
    assert len(result["source"]["tr_cards"]) >= 1
    assert result["source"]["guess"] != "point_like"
    assert result["source"]["guess"] == "disk_or_area"


def test_source_guess_sur_is_disk_or_area():
    text = deck("test", "sdef sur=1 par=2", "f8:p,e 1", "nps 100")
    result = inspect_deck(text)
    assert result["source"]["guess"] == "disk_or_area"


def test_source_guess_cel_is_cell_source():
    text = deck("test", "sdef cel=1 par=2", "f8:p,e 1", "nps 100")
    result = inspect_deck(text)
    assert result["source"]["guess"] == "cell_source"


def test_source_guess_unknown_without_pos_rad_sur_cel():
    text = deck("test", "sdef par=2 erg=0.662", "f8:p,e 1", "nps 100")
    result = inspect_deck(text)
    assert result["source"]["guess"] == "unknown"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_inspect_deck_outputs_json(tmp_path: Path):
    deck_path = tmp_path / "model.txt"
    deck_path.write_text(FULL_DECK, encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "inspect-deck",
            "--input", str(deck_path),
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["nps"]["present"] is True
    assert payload["geb"]["present"] is True
    assert completed.stderr == ""


def test_cli_inspect_deck_file_not_found(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "inspect-deck",
            "--input", str(tmp_path / "missing.txt"),
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("does not exist" in e for e in payload["errors"])
