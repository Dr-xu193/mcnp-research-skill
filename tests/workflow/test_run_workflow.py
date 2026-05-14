"""Tests for workflow run layer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.workflow.run import run_workflow


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
# dry-run
# ---------------------------------------------------------------------------


def test_dry_run_ok(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none", execute=False,
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["run"]["status"] == "skipped_dry_run"


# ---------------------------------------------------------------------------
# execute without confirm → blocked
# ---------------------------------------------------------------------------


def test_execute_without_confirm_blocked(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
        execute=True, confirm_mpi=False,
    )
    assert result["ok"] is False
    assert any(e.get("code") == "MISSING_CONFIRM_MPI" for e in result["errors"] if isinstance(e, dict))


# ---------------------------------------------------------------------------
# execute + confirm but no mpi_command → blocked
# ---------------------------------------------------------------------------


def test_execute_without_mpi_config_blocked(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
        execute=True, confirm_mpi=True, mpi_command=None,
    )
    assert result["ok"] is False
    assert any(e.get("code") == "MISSING_MPI_CONFIG" for e in result["errors"] if isinstance(e, dict))


# ---------------------------------------------------------------------------
# prepare blocked → no runner call
# ---------------------------------------------------------------------------


def test_prepare_blocked_no_runner(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f4:n 1", "nps 100"))
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="csv",
        execute=False,
    )
    assert result["ok"] is False
    assert any("CSV_REQUIRES_F8" in str(b) for b in result["blocked"])


# ---------------------------------------------------------------------------
# input not found
# ---------------------------------------------------------------------------


def test_input_not_found(tmp_path: Path):
    result = run_workflow(
        input_path=tmp_path / "missing.txt", work_dir=tmp_path / "work",
        workflow_mode="run-only", execute=False,
    )
    assert result["ok"] is False
    assert any("does not exist" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# patch-and-run + nps + dry-run → NPS changed in prepared deck
# ---------------------------------------------------------------------------


def test_patch_and_run_dry_run_nps_patched(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="patch-and-run",
        source_strategy="preserve_existing_source",
        nps="1e7", execute=False,
    )
    assert result["ok"] is True
    assert result["executed"] is False
    patched = (wd / "A.txt").read_text(encoding="utf-8")
    assert "nps 10000000" in patched
    assert "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662" in patched


# ---------------------------------------------------------------------------
# run-only + no tally + postprocess none → ok
# ---------------------------------------------------------------------------


def test_run_only_no_tally_ok(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "nps 100"))
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none", execute=False,
    )
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# execute + confirm + mpi_command → runner called (monkeypatch)
# ---------------------------------------------------------------------------


def test_execute_calls_runner_with_input_files(tmp_path: Path, monkeypatch):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    wd.mkdir(parents=True, exist_ok=True)
    # Must create the prepared file first so runner finds it
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    prepare_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
    )

    calls: list[dict] = []

    def fake_runner(**kwargs):
        calls.append(dict(kwargs))
        return {"ok": True, "commands": [], "completed": [], "failed": [], "warnings": [], "errors": []}

    monkeypatch.setattr("mcnp_research_skill.workflow.run.run_mpi_batch", fake_runner)

    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
        execute=True, confirm_mpi=True,
        mpi_command="mpirun -np 1 mcnp",
    )
    assert result["ok"] is True
    assert result["executed"] is True
    assert len(calls) == 1
    assert calls[0]["input_files"] == ["A.txt"]
    assert calls[0]["confirm"] is True


# ---------------------------------------------------------------------------
# runner exception → caught
# ---------------------------------------------------------------------------


def test_runner_exception_caught(tmp_path: Path, monkeypatch):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"

    def fake_crash(**kwargs):
        raise RuntimeError("MPI crash simulation")

    monkeypatch.setattr("mcnp_research_skill.workflow.run.run_mpi_batch", fake_crash)

    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
        execute=True, confirm_mpi=True,
        mpi_command="mpirun -np 1 mcnp",
    )
    assert result["ok"] is False
    assert result["run"]["status"] == "failed"
    assert any(e.get("code") == "RUNNER_FAILED" for e in result["errors"] if isinstance(e, dict))
    assert any("MPI crash" in str(e) for e in result["errors"])


# ---------------------------------------------------------------------------
# postprocess=csv-and-plot + F8 + dry-run → ok, not executed
# ---------------------------------------------------------------------------


def test_postprocess_csv_and_plot_dry_run(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f8:p,e 1", "nps 100"))
    wd = tmp_path / "work"
    result = run_workflow(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="csv-and-plot", execute=False,
    )
    assert result["ok"] is True
    assert result["executed"] is False
    assert result["postprocess_status"] == "planned_not_executed"


# ---------------------------------------------------------------------------
# CLI run-workflow
# ---------------------------------------------------------------------------


def test_cli_run_workflow_dry_run(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "run-workflow",
         "--input", str(inp), "--work-dir", str(wd),
         "--workflow-mode", "run-only", "--dry-run"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True


def test_cli_run_workflow_execute_no_confirm(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "run-workflow",
         "--input", str(inp), "--work-dir", str(wd),
         "--workflow-mode", "run-only", "--execute"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("MISSING_CONFIRM_MPI" in str(e) for e in payload["errors"])


def test_cli_run_workflow_execute_no_mpi_config(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "run-workflow",
         "--input", str(inp), "--work-dir", str(wd),
         "--workflow-mode", "run-only", "--execute", "--confirm-mpi"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("MISSING_MPI_CONFIG" in str(e) for e in payload["errors"])


def test_cli_run_workflow_prepare_blocked_no_runner(tmp_path: Path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "f4:n 1", "nps 100"))
    wd = tmp_path / "work"

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "run-workflow",
         "--input", str(inp), "--work-dir", str(wd),
         "--workflow-mode", "run-only", "--postprocess", "csv", "--dry-run"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("CSV_REQUIRES_F8" in str(b) for b in payload.get("blocked", []))


def test_cli_execute_mock_runner_does_not_run_mcnp(tmp_path: Path):
    """Use programmatic call (not subprocess) since monkeypatch cannot cross the boundary."""
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"

    from mcnp_research_skill.workflow.run import run_workflow as rw
    from mcnp_research_skill.cli import load_config

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text('mpi_command: "echo"\n', encoding="utf-8")

    mpi_cfg = load_config(str(cfg))
    result = rw(
        input_path=inp, work_dir=wd,
        workflow_mode="run-only", postprocess="none",
        execute=True, confirm_mpi=True,
        mpi_command=str(mpi_cfg["mpi_command"]),
    )
    # Real runner may fail (no MCNP installed), so just check safety gates passed
    # and runner was attempted (not blocked by MISSING_CONFIRM or MISSING_CONFIG)
    assert not any(
        e.get("code") in ("MISSING_CONFIRM_MPI", "MISSING_MPI_CONFIG")
        for e in result.get("errors", []) if isinstance(e, dict)
    )


# ---------------------------------------------------------------------------
# postprocess wiring
# ---------------------------------------------------------------------------


def test_dry_run_postprocess_csv_not_executed(tmp_path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    result = run_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only",
                          postprocess="csv", execute=False)
    assert result["ok"] is True
    assert result["postprocess_status"] == "planned_not_executed"
    assert "csv" not in result.get("artifacts", {})


def test_execute_success_calls_postprocess(tmp_path, monkeypatch):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    wd.mkdir(parents=True, exist_ok=True)
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    prepare_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only")

    runner_calls = []
    def fake_runner(**kw):
        runner_calls.append(kw)
        return {"ok": True, "commands": [], "completed": [{"output_path": str(wd / "A.out")}], "failed": [], "warnings": [], "errors": []}
    monkeypatch.setattr("mcnp_research_skill.workflow.run.run_mpi_batch", fake_runner)

    pp_calls = []
    def fake_pp(**kw):
        pp_calls.append(kw)
        return {"ok": True, "artifacts": {"csv": str(wd / "spectrum.csv")}, "blocked": [], "errors": [], "warnings": []}
    monkeypatch.setattr("mcnp_research_skill.workflow.run.postprocess_workflow", fake_pp)

    result = run_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only",
                          postprocess="csv", execute=True, confirm_mpi=True,
                          mpi_command="echo")
    assert result["ok"] is True
    assert result["postprocess_status"] == "completed"
    assert len(pp_calls) == 1
    # mcnp_output_path from runner completed
    assert str(pp_calls[0]["mcnp_output_path"]) == str(wd / "A.out")


def test_execute_success_postprocess_missing_output(tmp_path, monkeypatch):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    wd.mkdir(parents=True, exist_ok=True)
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    prepare_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only")

    def fake_runner(**kw):
        return {"ok": True, "commands": [], "completed": [], "failed": [], "warnings": [], "errors": []}
    monkeypatch.setattr("mcnp_research_skill.workflow.run.run_mpi_batch", fake_runner)

    # Explicitly pass a non-existent output path
    result = run_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only",
                          postprocess="csv", execute=True, confirm_mpi=True,
                          mpi_command="echo", mcnp_output_path=str(wd / "nope.txt"))
    assert result["ok"] is False
    assert result["postprocess_status"] == "failed"
    assert any(
        e.get("code") == "MISSING_MCNP_OUTPUT"
        for e in result.get("errors", []) if isinstance(e, dict)
    )


def test_execute_runner_failed_skips_postprocess(tmp_path, monkeypatch):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    wd.mkdir(parents=True, exist_ok=True)
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    prepare_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only")

    def fake_runner(**kw):
        return {"ok": False, "errors": ["MPI crashed"], "warnings": [], "completed": [], "failed": []}
    monkeypatch.setattr("mcnp_research_skill.workflow.run.run_mpi_batch", fake_runner)

    pp_called = []
    def fake_pp(**kw): pp_called.append(1); return {"ok": True}
    monkeypatch.setattr("mcnp_research_skill.workflow.run.postprocess_workflow", fake_pp)

    result = run_workflow(input_path=inp, work_dir=wd, workflow_mode="run-only",
                          postprocess="csv", execute=True, confirm_mpi=True,
                          mpi_command="echo")
    assert result["ok"] is False
    assert len(pp_called) == 0


def test_cli_run_workflow_dry_run_postprocess_planned(tmp_path):
    inp = _write_input(tmp_path / "A.txt", F8_DECK)
    wd = tmp_path / "work"
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "run-workflow",
        "--input", str(inp), "--work-dir", str(wd), "--workflow-mode", "run-only",
        "--postprocess", "csv", "--dry-run"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["postprocess_status"] == "planned_not_executed"


def test_run_workflow_point_sdef_pos_dry_run(tmp_path):
    inp = _write_input(tmp_path / "A.txt", deck("test", "sdef old source", "nps 100000"))
    wd = tmp_path / "work"
    r = run_workflow(input_path=inp, work_dir=wd, workflow_mode="patch-and-run",
                     source_strategy="point_sdef_pos",
                     source_position=[0, 0, 10], source_energy=0.662, execute=False)
    assert r["ok"] is True
    assert r["executed"] is False
    text = (wd / "A.txt").read_text(encoding="utf-8")
    assert "sdef pos=0 0 10 par=2 erg=0.662" in text
