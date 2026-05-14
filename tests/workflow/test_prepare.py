"""Tests for workflow prepare layer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.workflow.prepare import prepare_workflow


def deck(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def _write_input(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


F8_DECK = deck(
    "test",
    "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662",
    "si1 0 0.15",
    "sp1 -21 1",
    "TR1 0 0 -16.1900",
    "f8:p,e 1",
    "nps 100000",
)


# ---------------------------------------------------------------------------
# run-only + F4 + postprocess none → ok, no F4 block
# ---------------------------------------------------------------------------


def test_prepare_run_only_f4_postprocess_none(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f4:n 1", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
    )
    assert result["ok"] is True
    assert (wd / "A.txt").exists()
    assert "f4:n 1" in (wd / "A.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# run-only + no tally + postprocess none → ok
# ---------------------------------------------------------------------------


def test_prepare_run_only_no_tally_postprocess_none(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
    )
    assert result["ok"] is True
    assert (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# patch-and-run + preserve_existing_source + nps=1e7 → NPS changed
# ---------------------------------------------------------------------------


def test_prepare_patch_nps_preserves_source(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="patch-and-run",
        source_strategy="preserve_existing_source",
        nps="1e7",
    )
    assert result["ok"] is True
    assert result["changed"] is True
    patched = (wd / "A.txt").read_text(encoding="utf-8")
    assert "nps 10000000" in patched
    assert "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662" in patched
    assert "si1 0 0.15" in patched
    assert "sp1 -21 1" in patched
    assert "TR1 0 0 -16.1900" in patched


# ---------------------------------------------------------------------------
# patch-and-run without source_strategy → blocked
# ---------------------------------------------------------------------------


def test_prepare_patch_and_run_missing_source_strategy(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f8:p,e 1", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="patch-and-run", source_strategy=None,
    )
    assert result["ok"] is False
    assert any("MISSING_SOURCE_STRATEGY" in str(b) for b in result["blocked"])
    assert not (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# F4 + postprocess csv → blocked
# ---------------------------------------------------------------------------


def test_prepare_f4_postprocess_csv_blocked(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f4:n 1", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="csv",
    )
    assert result["ok"] is False
    assert any("CSV_REQUIRES_F8" in str(b) for b in result["blocked"])
    assert not (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# no tally + postprocess csv → blocked
# ---------------------------------------------------------------------------


def test_prepare_no_tally_postprocess_csv_blocked(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="csv",
    )
    assert result["ok"] is False
    assert any("NO_SUPPORTED_TALLY_FOR_CSV" in str(b) for b in result["blocked"])
    assert not (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# F8 + no GEB + postprocess csv → ok
# ---------------------------------------------------------------------------


def test_prepare_no_geb_postprocess_csv_ok(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f8:p,e 1", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="csv",
    )
    assert result["ok"] is True
    assert (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# multiple NPS → blocked
# ---------------------------------------------------------------------------


def test_prepare_multiple_nps_blocked(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f8:p,e 1", "nps 100", "nps 200"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
    )
    assert result["ok"] is False
    assert any("MULTIPLE_NPS" in str(b) for b in result["blocked"])
    assert not (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# unsupported source_strategy + nps → patch error, blocked
# ---------------------------------------------------------------------------


def test_prepare_unsupported_strategy_with_nps(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f8:p,e 1", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="patch-and-run",
        source_strategy="point_sdef_pos", nps=1000,
    )
    assert result["ok"] is False
    assert not (wd / "A.txt").exists()


# ---------------------------------------------------------------------------
# artifacts written on success
# ---------------------------------------------------------------------------


def test_prepare_writes_artifacts(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f8:p,e 1", "nps 100"))
    wd = tmp_path / "work"
    result = prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="csv",
    )
    assert result["ok"] is True
    assert (wd / "A.txt").exists()
    assert (wd / "inspection.json").exists()
    assert (wd / "plan.json").exists()
    assert (wd / "manifest.json").exists()


# ---------------------------------------------------------------------------
# CLI prepare-workflow
# ---------------------------------------------------------------------------


def test_cli_prepare_workflow_success(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "prepare-workflow",
         "--input", str(inp), "--work-dir", str(wd),
         "--workflow-mode", "patch-and-run",
         "--source-strategy", "preserve_existing_source",
         "--nps", "1e7"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["changed"] is True
    assert (wd / "A.txt").exists()
    assert (wd / "manifest.json").exists()


def test_cli_prepare_workflow_file_not_found(tmp_path: Path):
    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "prepare-workflow",
         "--input", str(tmp_path / "missing.txt"),
         "--work-dir", str(tmp_path / "out"),
         "--workflow-mode", "run-only"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False


def test_cli_prepare_blocked_does_not_write_input(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f4:n 1", "nps 100"))
    wd = tmp_path / "work"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "prepare-workflow",
         "--input", str(inp), "--work-dir", str(wd),
         "--workflow-mode", "run-only", "--postprocess", "csv"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert not (wd / "A.txt").exists()
