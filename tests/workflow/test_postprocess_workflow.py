"""Tests for workflow postprocess adapter."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from mcnp_research_skill.workflow.postprocess import postprocess_workflow

def deck(*lines): return "\n".join(lines) + "\n"

F8_DECK = deck("test", "f8:p,e 1", "nps 100")
F4_DECK = deck("test", "f4:n 1", "nps 100")
NO_TALLY_DECK = deck("test", "nps 100")

MCNP_OUT = "header\n     energy\n  0.100  1.0  0.01\n  0.200  2.0  0.02\n total  3.0  0.01\n"


# ---- F8 + mode=csv ----
def test_f8_csv_ok(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text(MCNP_OUT, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv", mcnp_output_path=out)
    assert r["ok"]; assert "csv" in r["artifacts"]
    csv_path = Path(r["artifacts"]["csv"])
    assert csv_path.exists()
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "Energy" in text; assert "0.1" in text


# ---- F8 + mode=csv-and-plot ----
def test_f8_csv_and_plot_ok(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text(MCNP_OUT, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv-and-plot", mcnp_output_path=out)
    assert r["ok"]
    assert "csv" in r["artifacts"]; assert "plot" in r["artifacts"]
    assert Path(r["artifacts"]["csv"]).exists()
    assert Path(r["artifacts"]["plot"]).exists()


# ---- F8 + no GEB + csv -> ok ----
def test_f8_no_geb_csv_ok(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text(MCNP_OUT, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv", mcnp_output_path=out)
    assert r["ok"]; assert r["inspection_summary"]["geb_present"] is False


# ---- F4 blocked ----
def test_f4_blocked(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F4_DECK, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv", mcnp_output_path=tmp_path / "out.txt")
    assert r["ok"] is False
    assert any(b.get("code") == "CSV_REQUIRES_F8" for b in r["blocked"])


# ---- no tally blocked ----
def test_no_tally_blocked(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(NO_TALLY_DECK, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv", mcnp_output_path=tmp_path / "out.txt")
    assert r["ok"] is False
    assert any(b.get("code") == "NO_SUPPORTED_TALLY_FOR_CSV" for b in r["blocked"])


# ---- missing mcnp output ----
def test_missing_output(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv", mcnp_output_path=tmp_path / "nope.txt")
    assert r["ok"] is False
    assert any(e.get("code") == "MISSING_MCNP_OUTPUT" for e in r["errors"] if isinstance(e, dict))


# ---- extract exception caught ----
def test_extract_exception_caught(tmp_path, monkeypatch):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text("garbage", encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    from mcnp_research_skill.workflow import postprocess as pp
    def fail_extract(path): raise RuntimeError("extraction failed")
    monkeypatch.setattr(pp, "_extract_rows", fail_extract)
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv", mcnp_output_path=out)
    assert r["ok"] is False
    assert any(e.get("code") == "EXTRACT_FAILED" for e in r["errors"] if isinstance(e, dict))


# ---- plot exception caught ----
def test_plot_exception_caught(tmp_path, monkeypatch):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text(MCNP_OUT, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    from mcnp_research_skill.workflow import postprocess as pp
    def fail_plot(**kw): raise RuntimeError("plot failed")
    monkeypatch.setattr(pp, "plot_spectra", fail_plot)
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="csv-and-plot", mcnp_output_path=out)
    assert r["ok"] is False
    assert any(e.get("code") == "PLOT_FAILED" for e in r["errors"] if isinstance(e, dict))


# ---- mode=plot generates csv dependency ----
def test_mode_plot_ok(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text(MCNP_OUT, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = postprocess_workflow(input_path=inp, work_dir=wd, mode="plot", mcnp_output_path=out)
    assert r["ok"]
    assert "plot" in r["artifacts"]
    # Plot mode still generates CSV as dependency
    assert Path(r["artifacts"]["plot"]).exists()


# ---- CLI csv ----
def test_cli_csv_ok(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    out = tmp_path / "results.txt"; out.write_text(MCNP_OUT, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "postprocess-workflow",
        "--input", str(inp), "--work-dir", str(wd), "--mode", "csv",
        "--mcnp-output", str(out)],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0
    p = json.loads(r.stdout); assert p["ok"]; assert "csv" in p["artifacts"]


# ---- CLI F4 blocked ----
def test_cli_f4_blocked(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F4_DECK, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "postprocess-workflow",
        "--input", str(inp), "--work-dir", str(wd), "--mode", "csv",
        "--mcnp-output", str(tmp_path / "out.txt")],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode != 0
    p = json.loads(r.stdout); assert p["ok"] is False
    assert any(b.get("code") == "CSV_REQUIRES_F8" for b in p.get("blocked", []))


# ---- CLI missing output ----
def test_cli_missing_output(tmp_path):
    inp = tmp_path / "deck.txt"; inp.write_text(F8_DECK, encoding="utf-8")
    wd = tmp_path / "work"; wd.mkdir()
    r = subprocess.run([sys.executable, "-m", "mcnp_research_skill.cli", "postprocess-workflow",
        "--input", str(inp), "--work-dir", str(wd), "--mode", "csv",
        "--mcnp-output", str(tmp_path / "nope.txt")],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode != 0
    p = json.loads(r.stdout); assert p["ok"] is False
    assert any(e.get("code") == "MISSING_MCNP_OUTPUT" for e in p.get("errors", []) if isinstance(e, dict))
