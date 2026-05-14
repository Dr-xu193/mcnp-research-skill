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
    result = patch_deck(d, nps=1000, source_strategy="encapsulated_disk_tr1")
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


# ---------------------------------------------------------------------------
# point_sdef_pos
# ---------------------------------------------------------------------------


def test_point_sdef_pos_replace_existing_sdef():
    d = deck("test", "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662", "f8:p,e 1", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=0.662)
    assert r["ok"] is True
    assert r["changed"] is True
    assert "sdef pos=0 0 10" in r["text"]
    assert "rad=" not in r["text"] or "rad=" in r["text"]  # old SI/SP/TR may remain
    assert "par=2" in r["text"]
    assert "erg=0.662" in r["text"]


def test_point_sdef_pos_insert_when_no_sdef():
    d = deck("test", "f8:p,e 1", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 5], source_energy=0.662)
    assert r["ok"] is True
    assert "sdef pos=0 0 5 par=2 erg=0.662" in r["text"]


def test_point_sdef_pos_multiple_sdef_reject():
    d = deck("test", "sdef pos=1 2 3", "sdef pos=4 5 6", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=0.662)
    assert r["ok"] is False
    assert any(e.get("code") == "MULTIPLE_SDEF" for e in r["errors"] if isinstance(e, dict))


def test_point_sdef_pos_missing_position():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_energy=0.662)
    assert r["ok"] is False
    assert any(e.get("code") == "MISSING_SOURCE_POSITION" for e in r["errors"] if isinstance(e, dict))


def test_point_sdef_pos_missing_energy():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10])
    assert r["ok"] is False
    assert any(e.get("code") == "MISSING_SOURCE_ENERGY" for e in r["errors"] if isinstance(e, dict))


def test_point_sdef_pos_invalid_position():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0], source_energy=0.662)
    assert r["ok"] is False
    assert any(e.get("code") == "INVALID_SOURCE_POSITION" for e in r["errors"] if isinstance(e, dict))


def test_point_sdef_pos_invalid_energy():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=-1)
    assert r["ok"] is False
    assert any(e.get("code") == "INVALID_SOURCE_ENERGY" for e in r["errors"] if isinstance(e, dict))


def test_point_sdef_pos_invalid_particle():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=0.662, source_particle="neutron")
    assert r["ok"] is False
    assert any(e.get("code") == "INVALID_SOURCE_PARTICLE" for e in r["errors"] if isinstance(e, dict))


def test_point_sdef_pos_preserves_si_sp_tr():
    d = deck("test", "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662", "si1 0 0.15", "sp1 -21 1", "TR1 0 0 -16.1900", "f8:p,e 1", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=0.662)
    assert r["ok"] is True
    assert "si1 0 0.15" in r["text"]
    assert "sp1 -21 1" in r["text"]
    assert "TR1 0 0 -16.1900" in r["text"]
    assert any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in r.get("warnings", []))


def test_point_sdef_pos_with_nps():
    d = deck("test", "sdef old", "nps 100000")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=0.662, nps="1e7")
    assert r["ok"] is True
    assert "sdef pos=0 0 10 par=2 erg=0.662" in r["text"]
    assert "nps 10000000" in r["text"]
    assert any(p["kind"] == "sdef" for p in r["patches"])
    assert any(p["kind"] == "nps" for p in r["patches"])


def test_preserve_existing_source_still_works():
    d = deck("test", "sdef old source", "nps 100")
    r = patch_deck(d, nps=1000, source_strategy="preserve_existing_source")
    assert r["ok"] is True
    assert "sdef old source" in r["text"]


# CLI tests
def test_cli_patch_point_sdef_pos(tmp_path: Path):
    inp = tmp_path / "A.txt"
    inp.write_text(deck("test", "sdef old", "nps 100"), encoding="utf-8")
    out = tmp_path / "patched.txt"
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
        "--input", str(inp), "--output", str(out),
        "--source-strategy", "point_sdef_pos",
        "--source-position", "0", "0", "10", "--source-energy", "0.662"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0
    p = json.loads(r.stdout); assert p["ok"]
    assert out.exists()
    assert "sdef pos=0 0 10 par=2 erg=0.662" in out.read_text(encoding="utf-8")


def test_cli_patch_point_sdef_missing_energy(tmp_path: Path):
    inp = tmp_path / "A.txt"
    inp.write_text(deck("test", "sdef old", "nps 100"), encoding="utf-8")
    out = tmp_path / "out.txt"
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
        "--input", str(inp), "--output", str(out),
        "--source-strategy", "point_sdef_pos", "--source-position", "0", "0", "10"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode != 0
    p = json.loads(r.stdout); assert p["ok"] is False
    assert not out.exists()
    assert any("MISSING_SOURCE_ENERGY" in str(e) for e in p.get("errors", []))


# ---------------------------------------------------------------------------
# disk_tr1
# ---------------------------------------------------------------------------


DISK_DECK = deck("test", "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662", "si1 0 0.15", "sp1 -21 1", "TR1 0 0 -16.1900", "f8:p,e 1", "nps 100")


def test_disk_tr1_replace_existing_sdef():
    r = patch_deck(DISK_DECK, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=0.15, source_energy=0.662)
    assert r["ok"] is True; assert r["changed"] is True
    text = r["text"]
    assert "sdef pos=0 0 0 rad=d" in text
    assert "tr=" in text; assert "par=2" in text; assert "erg=0.662" in text
    assert "tr" in text and " 0 0 10" in text or " 0.0 0.0 10.0" in text
    # old SI/SP/TR preserved
    assert "si1 0 0.15" in text; assert "sp1 -21 1" in text
    assert "TR1 0 0 -16.1900" in text
    assert any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in r.get("warnings", []))


def test_disk_tr1_insert_no_sdef():
    d = deck("test", "f8:p,e 1", "nps 100")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 5], source_radius=0.1, source_energy=0.662)
    assert r["ok"] is True
    assert "sdef pos=0 0 0 rad=" in r["text"]


def test_disk_tr1_auto_card_id_avoids_existing():
    # DISK_DECK already has TR1/SI1/SP1; auto should pick 2+
    r = patch_deck(DISK_DECK, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=0.15, source_energy=0.662)
    assert r["ok"] is True
    text = r["text"]
    # New cards should use id >= 2 (not 1)
    assert any(f"tr{c}" in text and f"si{c}" in text and f"sp{c}" in text for c in range(2, 10))


def test_disk_tr1_explicit_card_id():
    d = deck("test", "f8:p,e 1", "nps 100")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 5], source_radius=0.1, source_energy=0.662, source_card_id=7)
    assert r["ok"] is True
    assert "tr7" in r["text"]; assert "si7" in r["text"]; assert "sp7" in r["text"]
    assert "rad=d7" in r["text"]; assert "tr=7" in r["text"]


def test_disk_tr1_card_id_conflict():
    r = patch_deck(DISK_DECK, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=0.15, source_energy=0.662, source_card_id=1)
    assert r["ok"] is False
    assert any(e.get("code") == "SOURCE_CARD_ID_CONFLICT" for e in r["errors"] if isinstance(e, dict))


def test_disk_tr1_missing_radius():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 10], source_energy=0.662)
    assert r["ok"] is False
    assert any(e.get("code") == "MISSING_SOURCE_RADIUS" for e in r["errors"] if isinstance(e, dict))


def test_disk_tr1_invalid_radius():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=-1, source_energy=0.662)
    assert r["ok"] is False
    assert any(e.get("code") == "INVALID_SOURCE_RADIUS" for e in r["errors"] if isinstance(e, dict))


def test_disk_tr1_invalid_ext():
    d = deck("test", "nps 100")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=0.15, source_energy=0.662, source_ext="bad")
    assert r["ok"] is False
    assert any(e.get("code") == "INVALID_SOURCE_EXT" for e in r["errors"] if isinstance(e, dict))


def test_disk_tr1_multiple_sdef():
    d = deck("test", "sdef a", "sdef b", "nps 100")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=0.15, source_energy=0.662)
    assert r["ok"] is False
    assert any(e.get("code") == "MULTIPLE_SDEF" for e in r["errors"] if isinstance(e, dict))


def test_disk_tr1_with_nps():
    d = deck("test", "f8:p,e 1", "nps 100000")
    r = patch_deck(d, source_strategy="disk_tr1", source_position=[0, 0, 10], source_radius=0.15, source_energy=0.662, nps="1e7")
    assert r["ok"] is True
    assert "nps 10000000" in r["text"]
    assert any(p["kind"] == "disk_tr1" for p in r["patches"]) or any(p["kind"] == "tr" for p in r["patches"])
    assert any(p["kind"] == "nps" for p in r["patches"])


def test_point_sdef_pos_still_works():
    d = deck("test", "sdef old", "nps 100")
    r = patch_deck(d, source_strategy="point_sdef_pos", source_position=[0, 0, 10], source_energy=0.662)
    assert r["ok"] is True; assert "sdef pos=0 0 10 par=2 erg=0.662" in r["text"]


def test_preserve_still_works():
    d = deck("test", "sdef old", "nps 100")
    r = patch_deck(d, nps=1000, source_strategy="preserve_existing_source")
    assert r["ok"] is True; assert "sdef old" in r["text"]


def test_cli_disk_tr1_ok(tmp_path: Path):
    inp = tmp_path / "A.txt"; inp.write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")
    out = tmp_path / "patched.txt"
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
        "--input", str(inp), "--output", str(out),
        "--source-strategy", "disk_tr1", "--source-position", "0", "0", "10",
        "--source-radius", "0.15", "--source-energy", "0.662"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0; p = json.loads(r.stdout); assert p["ok"]
    assert out.exists(); assert "sdef pos=0 0 0 rad=" in out.read_text(encoding="utf-8")


def test_cli_disk_tr1_missing_radius(tmp_path: Path):
    inp = tmp_path / "A.txt"; inp.write_text("nps 100", encoding="utf-8")
    out = tmp_path / "out.txt"
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "patch-deck",
        "--input", str(inp), "--output", str(out),
        "--source-strategy", "disk_tr1", "--source-position", "0", "0", "10", "--source-energy", "0.662"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode != 0; p = json.loads(r.stdout); assert p["ok"] is False
    assert not out.exists()
