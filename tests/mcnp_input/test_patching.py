"""Tests for NPS-only deck patching."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.mcnp_input.patching import patch_deck, patch_deck_file


def deck(*lines: str) -> str:
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# single NPS replace
# ---------------------------------------------------------------------------


def test_single_nps_replace():
    d = deck("test", "f8:p,e 1", "nps 100000")
    result = patch_deck(d, nps="1e7")
    assert result["ok"] is True
    assert result["changed"] is True
    assert "nps 10000000" in result["text"]
    assert result["text"].count("nps ") == 1  # only one NPS line
    assert result["patches"][0]["kind"] == "nps"
    assert result["patches"][0]["action"] == "replace"


# ---------------------------------------------------------------------------
# no NPS → append
# ---------------------------------------------------------------------------


def test_no_nps_append():
    d = deck("test", "f8:p,e 1")
    result = patch_deck(d, nps=10000000)
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["text"].rstrip().endswith("nps 10000000")
    assert result["patches"][0]["action"] == "append"


# ---------------------------------------------------------------------------
# multiple NPS → reject
# ---------------------------------------------------------------------------


def test_multiple_nps_reject():
    d = deck("test", "f8:p,e 1", "nps 100", "c comment", "nps 200")
    result = patch_deck(d, nps=10000000)
    assert result["ok"] is False
    assert result["changed"] is False
    assert any(e.get("code") == "MULTIPLE_NPS" for e in result["errors"] if isinstance(e, dict))
    assert result["text"] == d


# ---------------------------------------------------------------------------
# scientific notation normalization
# ---------------------------------------------------------------------------


def test_nps_1e7_normalises():
    d = deck("test", "f8:p,e 1")
    result = patch_deck(d, nps="1e7")
    assert "nps 10000000" in result["text"]


def test_nps_1E7_normalises():
    d = deck("test", "f8:p,e 1")
    result = patch_deck(d, nps="1E7")
    assert "nps 10000000" in result["text"]


def test_nps_integer_unchanged():
    d = deck("test", "f8:p,e 1", "nps 500")
    result = patch_deck(d, nps=10000000)
    assert "nps 10000000" in result["text"]


# ---------------------------------------------------------------------------
# invalid NPS
# ---------------------------------------------------------------------------


def test_nps_negative_rejects():
    d = deck("test", "f8:p,e 1")
    result = patch_deck(d, nps=-1)
    assert result["ok"] is False
    assert any(e.get("code") == "INVALID_NPS" for e in result["errors"] if isinstance(e, dict))


def test_nps_unparseable_rejects():
    d = deck("test", "f8:p,e 1")
    result = patch_deck(d, nps="abc")
    assert result["ok"] is False
    assert any(e.get("code") == "INVALID_NPS" for e in result["errors"] if isinstance(e, dict))


# ---------------------------------------------------------------------------
# comment lines ignored
# ---------------------------------------------------------------------------


def test_comment_nps_ignored():
    d = deck("test", "c nps 100", "$ nps 100", "f8:p,e 1")
    result = patch_deck(d, nps=10000000)
    assert result["ok"] is True
    assert result["patches"][0]["action"] == "append"
    assert result["text"].count("nps") == 3  # 2 comments + 1 appended


# ---------------------------------------------------------------------------
# inline comment preserved
# ---------------------------------------------------------------------------


def test_inline_comment_preserved():
    d = deck("test", "f8:p,e 1", "nps 100000  $ old run count")
    result = patch_deck(d, nps=10000000)
    assert result["ok"] is True
    assert "nps 10000000  $ old run count" in result["text"]


# ---------------------------------------------------------------------------
# preserve_existing_source does not touch SDEF/SI/SP/TR
# ---------------------------------------------------------------------------


def test_preserve_source_cards_untouched():
    d = deck(
        "test deck",
        "mode p e",
        "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662",
        "si1 0 0.15",
        "sp1 -21 1",
        "TR1 0 0 -16.1900",
        "f8:p,e 1",
        "nps 100000",
    )
    result = patch_deck(d, nps=10000000, source_strategy="preserve_existing_source")
    assert result["ok"] is True
    assert "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662" in result["text"]
    assert "si1 0 0.15" in result["text"]
    assert "sp1 -21 1" in result["text"]
    assert "TR1 0 0 -16.1900" in result["text"]
    assert "mode p e" in result["text"]


# ---------------------------------------------------------------------------
# unsupported source strategy
# ---------------------------------------------------------------------------


def test_unsupported_source_strategy_rejects():
    d = deck("test", "f8:p,e 1", "nps 100")
    result = patch_deck(d, nps=1000, source_strategy="point_sdef_pos")
    assert result["ok"] is False
    assert result["changed"] is False
    assert any(
        e.get("code") == "UNSUPPORTED_SOURCE_STRATEGY"
        for e in result["errors"] if isinstance(e, dict)
    )
    assert result["text"] == d


# ---------------------------------------------------------------------------
# CLI patch-deck
# ---------------------------------------------------------------------------


def test_cli_patch_deck_writes_output(tmp_path: Path):
    inp = tmp_path / "model.txt"
    inp.write_text(deck("test", "f8:p,e 1", "nps 100000"), encoding="utf-8")
    out = tmp_path / "patched.txt"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
         "--input", str(inp), "--output", str(out), "--nps", "1e7"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["changed"] is True
    assert out.exists()
    assert "nps 10000000" in out.read_text(encoding="utf-8")
    # full deck text must not be in stdout
    assert '"text"' not in completed.stdout


def test_cli_patch_deck_file_not_found(tmp_path: Path):
    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
         "--input", str(tmp_path / "missing.txt"),
         "--output", str(tmp_path / "out.txt"), "--nps", "100"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False


def test_cli_patch_deck_multi_nps_does_not_write_output(tmp_path: Path):
    inp = tmp_path / "model.txt"
    inp.write_text(deck("test", "f8:p,e 1", "nps 100", "nps 200"), encoding="utf-8")
    out = tmp_path / "out.txt"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
         "--input", str(inp), "--output", str(out), "--nps", "1e6"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert not out.exists()
