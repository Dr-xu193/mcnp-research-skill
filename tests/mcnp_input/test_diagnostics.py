"""Tests for MCNP5 compatibility diagnostics / guided repair layer."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]
ROOT = Path.cwd()
FIXTURE = (
    ROOT / "mcnp_research_skill/models/fixtures/nai_3x3_verified.txt"
)


def _run(*args, tmp_path=None):
    return subprocess.run(
        CLI + list(args),
        cwd=str(tmp_path or ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _has_issue(issues, code):
    return any(i["code"] == code for i in issues)


def _issue_by_code(issues, code):
    for i in issues:
        if i["code"] == code:
            return i
    return None


# ==================================================================
# LINE_TOO_LONG
# ==================================================================

def test_diagnose_line_too_long():
    """A line > 80 columns must trigger LINE_TOO_LONG."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test deck\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "c " + "x" * 75 + " this exceeds eighty columns\n"
        "sdef pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "LINE_TOO_LONG")


def test_diagnose_line_too_long_not_triggered_under_80():
    """Short lines must not trigger LINE_TOO_LONG."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test deck\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "c short comment\n"
        "sdef pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "LINE_TOO_LONG")


def test_repair_line_too_long_continuation():
    """LINE_TOO_LONG on a data card should be repairable with continuation."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    # Build a line that definitely exceeds 80 columns
    long_sdef = "sdef pos=0 0 0 par=2 erg=0.662 x=0 y=0 z=10 rad=0.15 ext=0 cel=1 sur=2 vec=0 0 1 dir=1\n"
    assert len(long_sdef.rstrip()) > 80, f"precondition: line must exceed 80, got {len(long_sdef.rstrip())}"
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\n" + long_sdef + "nps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert result["repaired"] is True
    repaired = result["text"]
    assert "sdef" in repaired
    assert "par=2" in repaired
    assert "erg=0.662" in repaired
    for i, line in enumerate(repaired.split("\n"), 1):
        assert len(line.rstrip("\n")) <= 80, f"Line {i} exceeds 80: {len(line.rstrip())}"


def test_line_too_long_change_log():
    """Repair must produce a change log entry for LINE_TOO_LONG."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = (
        "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\n"
        + "c " + "y" * 75 + " over 80\n"
        + "nps 100\n"
    )
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert any(e["code"] == "LINE_TOO_LONG" for e in result["change_log"])


# ==================================================================
# TAB_CHARACTER
# ==================================================================

def test_diagnose_tab_character():
    """Tabs must trigger TAB_CHARACTER."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test deck\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "TAB_CHARACTER")


def test_repair_tab_replaces_with_spaces():
    """Repair must replace tabs with spaces."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert result["repaired"] is True
    assert "\t" not in result["text"]
    assert "sdef" in result["text"]
    cl = result["change_log"]
    assert any(e["code"] == "TAB_CHARACTER" for e in cl)


# ==================================================================
# Chinese comment cards
# ==================================================================

def test_legal_chinese_comment_card():
    """"c 中文注释" must be accepted (no NON_ASCII_DATA_CARD)."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test deck\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "c 这是一条中文注释\n"
        "sdef pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "NON_ASCII_DATA_CARD")
    # CHINESE_COMMENT_ENCODING_RISK is a warning, not blocking
    enc = _issue_by_code(result["issues"], "CHINESE_COMMENT_ENCODING_RISK")
    assert enc is None or enc["severity"] == "warning"


def test_chinese_comment_encoding_risk_warning():
    """Decks with Chinese should get CHINESE_COMMENT_ENCODING_RISK warning."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test deck 测试\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "sdef pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "CHINESE_COMMENT_ENCODING_RISK")


def test_bare_chinese_line_returns_non_ascii():
    """A bare Chinese line (not c comment, not $ comment) must trigger NON_ASCII_DATA_CARD."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test deck\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "这是裸中文行\n"
        "sdef pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "NON_ASCII_DATA_CARD")


def test_repair_bare_chinese_to_comment():
    """Repair must convert bare Chinese lines to c comment cards."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    # Use CJK codepoints via chr() to avoid source-file encoding issues
    cjk = chr(0x8FD9) + chr(0x662F) + chr(0x6D4B) + chr(0x8BD5)  # 这是测试
    deck = (
        "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\n" + cjk + "\nsdef pos=0 0 0\nnps 100\n"
    )
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    repaired = result["text"]
    assert "c " + cjk in repaired
    cl = result["change_log"]
    assert any(e["code"] == "NON_ASCII_DATA_CARD" for e in cl)


# ==================================================================
# INVALID_CONTINUATION
# ==================================================================

def test_invalid_continuation_comment():
    """A continuation line that is actually a comment must be flagged."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef pos=0 0 0 par=2\n"
        "     c this looks like continuation but is a comment\nnps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "INVALID_CONTINUATION")


# ==================================================================
# MISSING_BLOCK_DELIMITER
# ==================================================================

def test_missing_block_delimiter():
    """Deck without blank lines between sections may trigger warning."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    # No blank lines between sections
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef pos=0 0 0\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "MISSING_BLOCK_DELIMITER")


# ==================================================================
# UNKNOWN_TALLY_CELL_REFERENCE
# ==================================================================

def test_unknown_tally_cell_reference():
    """F8 tally referencing nonexistent cell must trigger UNKNOWN_TALLY_CELL_REFERENCE."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p e\n"
        "f8:p 999\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "UNKNOWN_TALLY_CELL_REFERENCE")
    iss = _issue_by_code(result["issues"], "UNKNOWN_TALLY_CELL_REFERENCE")
    assert iss["severity"] == "blocking"


def test_known_tally_cell_no_error():
    """F8 tally referencing existing cell must NOT trigger UNKNOWN_TALLY_CELL_REFERENCE."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "10 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p e\n"
        "f8:p 10\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "UNKNOWN_TALLY_CELL_REFERENCE")


# ==================================================================
# UNKNOWN_SURFACE_REFERENCE
# ==================================================================

def test_unknown_surface_reference():
    """Cell referencing nonexistent surface must trigger UNKNOWN_SURFACE_REFERENCE."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -99 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "UNKNOWN_SURFACE_REFERENCE")
    iss = _issue_by_code(result["issues"], "UNKNOWN_SURFACE_REFERENCE")
    assert iss["severity"] == "blocking"


def test_known_surface_no_error():
    """All surfaces defined must not trigger UNKNOWN_SURFACE_REFERENCE."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 2 imp:p=1\n"
        "1 so 100\n"
        "2 cz 5\n"
        "mode p\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "UNKNOWN_SURFACE_REFERENCE")


# ==================================================================
# UNKNOWN_MATERIAL_REFERENCE
# ==================================================================

def test_unknown_material_reference():
    """Cell referencing nonexistent material must trigger UNKNOWN_MATERIAL_REFERENCE."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 5 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "UNKNOWN_MATERIAL_REFERENCE")


def test_void_cell_no_material_error():
    """Material 0 (void) must not trigger UNKNOWN_MATERIAL_REFERENCE."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "UNKNOWN_MATERIAL_REFERENCE")


# ==================================================================
# MODE_TALLY_MISMATCH
# ==================================================================

def test_mode_tally_mismatch():
    """MODE p with F8:n must trigger MODE_TALLY_MISMATCH."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p\n"
        "f8:n 1\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "MODE_TALLY_MISMATCH")


def test_mode_tally_ok():
    """MODE p e with F8:p must NOT trigger MODE_TALLY_MISMATCH."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "mode p e\n"
        "f8:p,e 1\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "MODE_TALLY_MISMATCH")


# ==================================================================
# MODE_SOURCE_MISMATCH
# ==================================================================

def test_mode_source_mismatch():
    """MODE n with SDEF par=2 (photon) must trigger MODE_SOURCE_MISMATCH."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 imp:n=1\n"
        "1 so 100\n"
        "mode n\n"
        "sdef par=2 pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "MODE_SOURCE_MISMATCH")


# ==================================================================
# built-in fixture regression
# ==================================================================

def test_nai_3x3_fixture_diagnostics_ok():
    """nai_3x3_verified fixture must pass diagnostics with no blocking issues."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = diagnose_deck_file(str(resolve_deck_path("nai_3x3_verified")),
                                mcnp_version="mcnp5_rsicc_1_14")
    assert result["ok"] is True
    assert result["summary"]["blocking"] == 0


def test_nai_3x3_fixture_no_line_too_long():
    """Fixture must have no LINE_TOO_LONG issue."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = diagnose_deck_file(str(resolve_deck_path("nai_3x3_verified")),
                                mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "LINE_TOO_LONG")


def test_nai_3x3_fixture_no_tabs():
    """Fixture must have no TAB_CHARACTER issue."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = diagnose_deck_file(str(resolve_deck_path("nai_3x3_verified")),
                                mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "TAB_CHARACTER")


def test_nai_3x3_fixture_inspect_still_ok():
    """inspect-deck must still work on fixture."""
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = inspect_deck_file(str(resolve_deck_path("nai_3x3_verified")))
    assert result["ok"] is True
    assert result["errors"] == []


# ==================================================================
# diagnose structure
# ==================================================================

def test_issue_has_all_required_fields():
    """Every issue must have code, severity, line, message, ai_guidance, etc."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    for iss in result["issues"]:
        assert "code" in iss
        assert "severity" in iss
        assert iss["severity"] in ("warning", "error", "blocking")
        assert "line" in iss
        assert "message" in iss
        assert "mcnp_version" in iss
        assert "observed" in iss
        assert "expected" in iss
        assert "auto_fixable" in iss
        assert isinstance(iss["auto_fixable"], bool)
        assert "suggested_fix" in iss
        assert "user_explanation" in iss
        assert "ai_guidance" in iss
        ag = iss["ai_guidance"]
        assert "mcnp_version_assumed" in ag
        assert "topics_to_review" in ag
        assert isinstance(ag["topics_to_review"], list)
        assert "instruction" in ag


def test_summary_counts_match_issues():
    """Summary counts must match actual issues."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\n" + "x" * 85 + "\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    s = result["summary"]
    assert s["total"] == len(result["issues"])
    assert s["blocking"] == sum(1 for i in result["issues"] if i["severity"] == "blocking")
    assert s["errors"] == sum(1 for i in result["issues"] if i["severity"] == "error")
    assert s["warnings"] == sum(1 for i in result["issues"] if i["severity"] == "warning")
    assert s["fixable"] == sum(1 for i in result["issues"] if i["auto_fixable"])


# ==================================================================
# version profiles
# ==================================================================

def test_mcnp5_legacy_alias():
    """mcnp5_legacy must be an alias for mcnp5_rsicc_1_14."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    r1 = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    r2 = diagnose_deck(deck, mcnp_version="mcnp5_legacy")
    assert r1["summary"] == r2["summary"]


def test_unknown_version_falls_back():
    """Unknown mcnp_version must fall back to conservative rules."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="bogus_version_x")
    assert result["mcnp_version"] == "bogus_version_x"
    assert _has_issue(result["issues"], "TAB_CHARACTER")


# ==================================================================
# repair: no-touch boundaries
# ==================================================================

def test_repair_does_not_change_geometry():
    """Repair must not modify cell/surface geometry expressions."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "test\n1 0 -1 2 -3 #4 imp:p=1\n1 so 100\n2 cz 5\n3 pz 10\nmode p\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    # Geometry should be identical
    for kw in ("-1", "2", "-3", "#4", "so 100", "cz 5", "pz 10"):
        assert kw in result["text"]


def test_repair_does_not_change_material():
    """Repair must not modify material compositions."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "test\n1 1 -2.7 -1 imp:p=1\n1 so 100\nmode p\nm1 13000 -1.0\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert "m1 13000 -1.0" in result["text"]


def test_repair_does_not_change_tally():
    """Repair must not modify F tally definitions."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "test\n1 0 -1 imp:p=1 imp:e=1\n1 so 100\nmode p e\nf8:p,e 1\ne8 0 1024i 2.5\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert "f8:p,e 1" in result["text"]
    assert "e8 0 1024i 2.5" in result["text"]


def test_repair_does_not_change_source():
    """Repair must not modify SDEF source physics."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef pos=0 0 0 par=2 erg=0.662\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert "sdef pos=0 0 0 par=2 erg=0.662" in result["text"]


# ==================================================================
# CARD_START_COLUMN
# ==================================================================

def test_card_start_column_warning():
    """A card starting beyond column 5 should get a warning."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = (
        "test\n"
        "1 0 -1 imp:p=1\n"
        "1 so 100\n"
        "      mode p\n"  # card at column 7
        "sdef pos=0 0 0\n"
        "nps 100\n"
    )
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "CARD_START_COLUMN")


# ==================================================================
# CLI: diagnose-deck
# ==================================================================

def test_cli_diagnose_deck_json(tmp_path):
    """diagnose-deck must output structured JSON with issues."""
    (tmp_path / "A.txt").write_text(
        "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n",
        encoding="utf-8",
    )
    r = _run("--json", "diagnose-deck", "--input", str(tmp_path / "A.txt"),
             "--mcnp-version", "mcnp5_rsicc_1_14")
    # TAB_CHARACTER is error (not blocking), so ok=true
    p = json.loads(r.stdout)
    assert _has_issue(p["issues"], "TAB_CHARACTER")
    assert p["summary"]["errors"] >= 1


def test_cli_diagnose_deck_clean(tmp_path):
    """A clean deck must return ok=true with no issues."""
    (tmp_path / "A.txt").write_text(
        "test\n1 0 -1 imp:p=1\n1 so 100\n\nmode p\nsdef pos=0 0 0\nnps 100\n",
        encoding="utf-8",
    )
    r = _run("--json", "diagnose-deck", "--input", str(tmp_path / "A.txt"))
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"] is True
    assert p["summary"]["total"] == 0


# ==================================================================
# CLI: repair-deck
# ==================================================================

def test_cli_repair_deck(tmp_path):
    """repair-deck must output repaired file and change log."""
    (tmp_path / "A.txt").write_text(
        "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef\tpos=0 0 0\nnps 100\n",
        encoding="utf-8",
    )
    r = _run("--json", "repair-deck", "--input", str(tmp_path / "A.txt"),
             "--output", str(tmp_path / "repaired.txt"))
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"] is True
    assert p["repaired"] is True
    assert len(p["change_log"]) >= 1
    assert (tmp_path / "repaired.txt").exists()
    repaired_text = (tmp_path / "repaired.txt").read_text(encoding="utf-8")
    assert "\t" not in repaired_text


# ==================================================================
# CLI: inspect-deck --diagnostics
# ==================================================================

def test_cli_inspect_deck_with_diagnostics(tmp_path):
    """inspect-deck --diagnostics must include diagnostics key in output."""
    # Use an F8 deck so inspect passes (no NO_TALLY_CARD error)
    (tmp_path / "A.txt").write_text(
        "test\n1 0 -1 imp:p=1 imp:e=1\n1 so 100\n\nmode p e\nf8:p,e 1\nnps 100\n",
        encoding="utf-8",
    )
    r = _run("inspect-deck", "--input", str(tmp_path / "A.txt"), "--diagnostics")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"] is True
    assert "diagnostics" in p
    assert p["diagnostics"]["ok"] is True


# ==================================================================
# CLI: prepare-workflow --diagnostics blocks on error
# ==================================================================

def test_cli_prepare_diagnostics_blocking(tmp_path):
    """prepare-workflow --diagnostics with blocking issue must return ok=false."""
    # Cell references nonexistent surface → blocking
    deck = "test\n1 0 -99 imp:p=1\n1 so 100\n\nmode p\nnps 100\n"
    (tmp_path / "A.txt").write_text(deck, encoding="utf-8")
    r = _run("prepare-workflow", "--input", str(tmp_path / "A.txt"),
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "run-only",
             "--source-strategy", "preserve_existing_source",
             "--postprocess", "none",
             "--diagnostics")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert p["ok"] is False
    assert _has_issue(p["issues"], "UNKNOWN_SURFACE_REFERENCE")
    # Must NOT write prepared deck
    assert not (tmp_path / "w" / "A.txt").exists()


def test_cli_prepare_diagnostics_warning_proceeds(tmp_path):
    """prepare-workflow --diagnostics with only warnings must proceed."""
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nsdef pos=0 0 0\nnps 100\n"
    (tmp_path / "A.txt").write_text(deck, encoding="utf-8")
    r = _run("prepare-workflow", "--input", str(tmp_path / "A.txt"),
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "run-only",
             "--source-strategy", "preserve_existing_source",
             "--postprocess", "none",
             "--diagnostics")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"] is True


# ==================================================================
# workflow boundaries
# ==================================================================

def test_run_only_no_f8_not_blocked_by_diagnostics(tmp_path):
    """run-only without F8 must NOT be blocked by diagnostics (no tally requirement)."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\n\nmode p\nsdef pos=0 0 0\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert result["ok"] is True


def test_f4_csv_still_blocked_by_csv_requires_f8():
    """F4 + csv/plot must still be blocked by CSV_REQUIRES_F8 in plan-workflow."""
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.workflow.planner import plan_workflow

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\n\nmode p\nf4:p 1\nnps 100\n"
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "A.txt")
    Path(p).write_text(deck, encoding="utf-8")
    inspection = inspect_deck_file(p)
    plan = plan_workflow(inspection, workflow_mode="run-only",
                         source_strategy="preserve_existing_source",
                         postprocess="csv", requested_nps=None)
    assert any(b.get("code") == "CSV_REQUIRES_F8" for b in plan.get("blocked", []))


def test_execute_safety_gates_unchanged():
    """--execute without --confirm-mpi must still be blocked."""
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\n\nmode p\nsdef pos=0 0 0\nnps 100\n"
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "A.txt")
    Path(p).write_text(deck, encoding="utf-8")
    r = _run("run-workflow", "--input", p,
             "--work-dir", os.path.join(d, "w"),
             "--workflow-mode", "run-only",
             "--postprocess", "none",
             "--execute")
    assert r.returncode != 0
    p2 = json.loads(r.stdout)
    assert p2["ok"] is False
    assert any("MISSING_CONFIRM_MPI" in str(e) for e in p2.get("errors", []))


# ==================================================================
# NON_ASCII_TITLE_CARD
# ==================================================================

def test_diagnose_non_ascii_title_card():
    """Title line with non-ASCII (em dash) must trigger NON_ASCII_TITLE_CARD."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test title — with em dash\n1 0 -1 imp:p=1\n1 so 100\nmode p\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "NON_ASCII_TITLE_CARD")


def test_repair_non_ascii_title_punctuation():
    """Repair must replace em dash in title with '--'."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "test — title\n1 0 -1 imp:p=1\n1 so 100\nmode p\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert result["repaired"] is True
    first_line = result["text"].split("\n")[0]
    assert "—" not in first_line
    assert "--" in first_line
    cl = result["change_log"]
    assert any(e["code"] == "NON_ASCII_TITLE_CARD" for e in cl)


def test_repair_non_ascii_title_change_log_correct():
    """Change log must record before/after for title repair."""
    from mcnp_research_skill.mcnp_input.diagnostics import repair_deck

    deck = "title — mid\n1 0 -1 imp:p=1\n1 so 100\nmode p\nnps 100\n"
    result = repair_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    cl_entry = next((e for e in result["change_log"] if e["code"] == "NON_ASCII_TITLE_CARD"), None)
    assert cl_entry is not None
    assert "—" in cl_entry["before"]
    assert "—" not in cl_entry["after"]


# ==================================================================
# NON_ASCII_DATA_CARD
# ==================================================================

def test_diagnose_non_ascii_in_data_card():
    """Non-ASCII in a card that's not a comment must trigger NON_ASCII_DATA_CARD."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    # nps card with non-ASCII inline
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nnps 100  $ — note\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert _has_issue(result["issues"], "NON_ASCII_DATA_CARD")


def test_diagnose_non_ascii_not_silently_passed():
    """Non-ASCII in data card must NOT silently pass diagnostics."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    # A material card with non-ASCII
    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nm1 13000 — 1.0\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    issues = [i for i in result["issues"] if i["code"] == "NON_ASCII_DATA_CARD"]
    assert len(issues) >= 1
    # Should be error (in card content, not just inline comment)
    assert any(i["severity"] == "error" for i in issues)


# ==================================================================
# legal Chinese comment card still works
# ==================================================================

def test_chinese_comment_still_legal():
    """"c 中文注释" must not be flagged as NON_ASCII_DATA_CARD."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nc 中文注释\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert not _has_issue(result["issues"], "NON_ASCII_DATA_CARD")
    # Should get encoding risk warning
    assert _has_issue(result["issues"], "CHINESE_COMMENT_ENCODING_RISK")


def test_chinese_comment_not_blocking():
    """CHINESE_COMMENT_ENCODING_RISK must be warning, not blocking."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck

    deck = "test\n1 0 -1 imp:p=1\n1 so 100\nmode p\nc 中文\nnps 100\n"
    result = diagnose_deck(deck, mcnp_version="mcnp5_rsicc_1_14")
    assert result["ok"] is True  # not blocked
    enc = _issue_by_code(result["issues"], "CHINESE_COMMENT_ENCODING_RISK")
    assert enc is not None
    assert enc["severity"] == "warning"


# ==================================================================
# template fixture regression
# ==================================================================

def test_1x1_template_all_ascii():
    """1x1 template must have zero non-ASCII characters."""
    from mcnp_research_skill.models.registry import resolve_deck_path
    import re

    text = resolve_deck_path("nai_1x1_template").read_text(encoding="utf-8")
    non_ascii = re.findall(r"[^\x00-\x7F]", text)
    assert len(non_ascii) == 0, f"1x1 template has non-ASCII: {non_ascii!r}"


def test_2x2_template_all_ascii():
    """2x2 template must have zero non-ASCII characters."""
    from mcnp_research_skill.models.registry import resolve_deck_path
    import re

    text = resolve_deck_path("nai_2x2_template").read_text(encoding="utf-8")
    non_ascii = re.findall(r"[^\x00-\x7F]", text)
    assert len(non_ascii) == 0, f"2x2 template has non-ASCII: {non_ascii!r}"


def test_templates_non_comment_cards_ascii():
    """Template non-comment cards must all be ASCII."""
    from mcnp_research_skill.models.registry import resolve_deck_path
    import re

    for tid in ("nai_1x1_template", "nai_2x2_template"):
        lines = resolve_deck_path(tid).read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue
            # Skip comment cards
            if stripped.startswith(("c ", "C ")):
                continue
            non_ascii = re.findall(r"[^\x00-\x7F]", line)
            assert len(non_ascii) == 0, (
                f"{tid} line {i} non-comment has non-ASCII: {non_ascii!r}  "
                f"content: {line[:60]!r}"
            )


def test_templates_diagnostics_clean():
    """Both templates must pass diagnostics with zero errors."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    for tid in ("nai_1x1_template", "nai_2x2_template"):
        diag = diagnose_deck_file(
            str(resolve_deck_path(tid)), mcnp_version="mcnp5_rsicc_1_14"
        )
        assert diag["summary"]["blocking"] == 0, f"{tid} has blocking issues"
        assert diag["summary"]["errors"] == 0, f"{tid} has errors"


def test_templates_inspect_clean():
    """Both templates must pass inspect with zero errors."""
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    for tid in ("nai_1x1_template", "nai_2x2_template"):
        insp = inspect_deck_file(str(resolve_deck_path(tid)))
        assert insp["errors"] == [], f"{tid} inspect errors: {insp['errors']}"


# ==================================================================
# nai_3x3_verified regression
# ==================================================================

def test_nai_3x3_not_flagged_by_new_checks():
    """nai_3x3_verified must still pass diagnostics cleanly."""
    from mcnp_research_skill.mcnp_input.diagnostics import diagnose_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    diag = diagnose_deck_file(
        str(resolve_deck_path("nai_3x3_verified")), mcnp_version="mcnp5_rsicc_1_14"
    )
    assert diag["ok"] is True
    assert diag["summary"]["blocking"] == 0
    assert diag["summary"]["errors"] == 0
    assert not _has_issue(diag["issues"], "NON_ASCII_TITLE_CARD")
    assert not _has_issue(diag["issues"], "NON_ASCII_DATA_CARD")
