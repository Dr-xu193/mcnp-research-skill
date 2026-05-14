"""Tests for workflow preflight planner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.mcnp_input.inspection import inspect_deck
from mcnp_research_skill.workflow.planner import plan_workflow


def deck(*lines: str) -> str:
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# run-only + F4 + postprocess none  →  ok, not blocked by F4
# ---------------------------------------------------------------------------


def test_run_only_f4_postprocess_none():
    d = deck("test", "f4:n 1", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="none")
    assert result["ok"] is True
    assert result["capabilities"]["can_run"] is True


# ---------------------------------------------------------------------------
# run-only + no tally + postprocess none  →  ok, NO_TALLY_CARD does not block
# ---------------------------------------------------------------------------


def test_run_only_no_tally_postprocess_none():
    d = deck("test", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="none")
    assert result["ok"] is True
    assert result["capabilities"]["can_run"] is True


# ---------------------------------------------------------------------------
# F4 deck + postprocess csv  →  blocked CSV_REQUIRES_F8
# ---------------------------------------------------------------------------


def test_f4_postprocess_csv_blocked():
    d = deck("test", "f4:n 1", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="csv")
    assert result["ok"] is False
    assert any(b.get("code") == "CSV_REQUIRES_F8" for b in result["blocked"])


# ---------------------------------------------------------------------------
# no tally + postprocess csv  →  blocked NO_SUPPORTED_TALLY_FOR_CSV
# ---------------------------------------------------------------------------


def test_no_tally_postprocess_csv_blocked():
    d = deck("test", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="csv")
    assert result["ok"] is False
    assert any(b.get("code") == "NO_SUPPORTED_TALLY_FOR_CSV" for b in result["blocked"])


# ---------------------------------------------------------------------------
# F8 deck + postprocess csv-and-plot  →  ok
# ---------------------------------------------------------------------------


def test_f8_postprocess_csv_and_plot_ok():
    d = deck("test", "f8:p,e 1", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="csv-and-plot")
    assert result["ok"] is True
    assert result["capabilities"]["can_extract_csv"] is True
    assert result["capabilities"]["can_plot"] is True


# ---------------------------------------------------------------------------
# no GEB + F8 + postprocess csv  →  ok (no GEB is not an error)
# ---------------------------------------------------------------------------


def test_no_geb_postprocess_csv_ok():
    d = deck("test", "f8:p,e 1", "e8 0 1024i 2.5", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="csv")
    assert result["ok"] is True
    # GEB not present, but that is fine
    assert insp["geb"]["present"] is False


# ---------------------------------------------------------------------------
# patch-and-run without source_strategy  →  blocked
# ---------------------------------------------------------------------------


def test_patch_and_run_missing_source_strategy():
    d = deck("test", "f8:p,e 1", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="patch-and-run", source_strategy=None)
    assert result["ok"] is False
    assert any(b.get("code") == "MISSING_SOURCE_STRATEGY" for b in result["blocked"])


# ---------------------------------------------------------------------------
# patch-and-run + preserve_existing_source + --nps  →  actions include patch_nps
# ---------------------------------------------------------------------------


def test_patch_and_run_preserve_with_nps():
    d = deck("test", "f8:p,e 1", "nps 100")
    insp = inspect_deck(d)
    result = plan_workflow(
        insp, workflow_mode="patch-and-run",
        source_strategy="preserve_existing_source", requested_nps=200,
    )
    assert result["ok"] is True
    actions = [a["step"] for a in result["actions"]]
    assert "patch_nps" in actions


# ---------------------------------------------------------------------------
# multiple NPS  →  blocked
# ---------------------------------------------------------------------------


def test_multiple_nps_blocked():
    d = deck("test", "f8:p,e 1", "nps 100", "nps 200")
    insp = inspect_deck(d)
    result = plan_workflow(insp, workflow_mode="run-only", postprocess="none")
    assert result["ok"] is False
    assert any(b.get("code") == "MULTIPLE_NPS" for b in result["blocked"])


# ---------------------------------------------------------------------------
# CLI plan-workflow
# ---------------------------------------------------------------------------


def _write_plan_deck(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_cli_plan_workflow_outputs_json(tmp_path: Path):
    p = _write_plan_deck(tmp_path / "model.txt", deck("test", "f8:p,e 1", "nps 100"))

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "plan-workflow",
         "--input", str(p), "--workflow-mode", "run-only", "--postprocess", "csv-and-plot"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["capabilities"]["can_extract_csv"] is True


def test_cli_plan_workflow_file_not_found(tmp_path: Path):
    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "plan-workflow",
         "--input", str(tmp_path / "missing.txt"), "--workflow-mode", "run-only"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("does not exist" in e for e in payload["errors"])


def test_cli_plan_workflow_f4_postprocess_csv_blocked(tmp_path: Path):
    p = _write_plan_deck(tmp_path / "model.txt", deck("test", "f4:n 1", "nps 100"))

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "plan-workflow",
         "--input", str(p), "--workflow-mode", "run-only", "--postprocess", "csv"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any(b.get("code") == "CSV_REQUIRES_F8" for b in payload["blocked"])
