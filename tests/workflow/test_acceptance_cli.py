"""User-level acceptance CLI tests.  No real MCNP/MPI execution."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]
ROOT = Path.cwd()

F8 = "title\nmode p e\nsdef pos=0 0 0 par=2 erg=0.662\nf8:p,e 1\ne8 0 0.1 1.0\nnps 100000\n"
F4 = "title\nmode p\nsdef pos=0 0 0 par=2 erg=0.662\nf4:p 1\nnps 100000\n"
NO_TALLY = "title\nmode p\nsdef pos=0 0 0 par=2 erg=0.662\nnps 100000\n"

def _run(*args, tmp_path=None):
    return subprocess.run(CLI + list(args), cwd=str(tmp_path or ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# ---- inspect-deck ----
def test_inspect_f8_deck(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=_run("inspect-deck","--input",str(tmp_path/"A.txt"))
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
    assert any(t["kind"]=="F8" for t in p["tallies"])

# ---- plan-workflow ----
def test_plan_run_only_f4_postprocess_none(tmp_path):
    (tmp_path/"A.txt").write_text(F4,encoding="utf-8")
    r=_run("plan-workflow","--input",str(tmp_path/"A.txt"),"--workflow-mode","run-only","--postprocess","none")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]

def test_plan_f4_postprocess_csv_blocked(tmp_path):
    (tmp_path/"A.txt").write_text(F4,encoding="utf-8")
    r=_run("plan-workflow","--input",str(tmp_path/"A.txt"),"--workflow-mode","run-only","--postprocess","csv")
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False
    assert any(b.get("code")=="CSV_REQUIRES_F8" for b in p.get("blocked",[]))

# ---- patch-deck ----
def test_patch_preserve_nps(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nsdef old source\nnps 100000\n",encoding="utf-8")
    out=tmp_path/"patched.txt"
    r=_run("patch-deck","--input",str(inp),"--output",str(out),"--nps","1e7")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
    assert "nps 10000000" in out.read_text(encoding="utf-8")
    assert "sdef old source" in out.read_text(encoding="utf-8")

# ---- disk_tr1 acceptance ----


def test_patch_disk_tr1_generates_tr_si_sp(tmp_path):
    inp = tmp_path / "A.txt"; inp.write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")
    out = tmp_path / "patched.txt"
    r = _run("patch-deck", "--input", str(inp), "--output", str(out),
             "--source-strategy", "disk_tr1", "--source-position", "0", "0", "10",
             "--source-radius", "0.15", "--source-energy", "0.662")
    assert r.returncode == 0; p = json.loads(r.stdout); assert p["ok"]
    text = out.read_text(encoding="utf-8")
    assert "sdef pos=0 0 0 rad=d" in text
    assert "tr=" in text and "par=2" in text and "erg=0.662" in text
    assert "si" in text and "sp" in text


def test_patch_disk_tr1_auto_card_id_avoids_existing(tmp_path):
    inp = tmp_path / "A.txt"
    inp.write_text("f8:p,e 1\nnps 100\nsi1 0 0.15\nsp1 -21 1\nTR1 0 0 -16\n", encoding="utf-8")
    out = tmp_path / "patched.txt"
    r = _run("patch-deck", "--input", str(inp), "--output", str(out),
             "--source-strategy", "disk_tr1", "--source-position", "0", "0", "10",
             "--source-radius", "0.15", "--source-energy", "0.662")
    assert r.returncode == 0; p = json.loads(r.stdout); assert p["ok"]
    text = out.read_text(encoding="utf-8")
    # New cards should use id >= 2 since 1 is taken
    assert "tr2" in text or "tr3" in text


def test_patch_disk_tr1_card_id_conflict(tmp_path):
    inp = tmp_path / "A.txt"
    inp.write_text("tr5 1 2 3\nnps 100\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    r = _run("patch-deck", "--input", str(inp), "--output", str(out),
             "--source-strategy", "disk_tr1", "--source-position", "0", "0", "10",
             "--source-radius", "0.15", "--source-energy", "0.662", "--source-card-id", "5")
    assert r.returncode != 0; p = json.loads(r.stdout); assert p["ok"] is False
    assert any(e.get("code") == "SOURCE_CARD_ID_CONFLICT" for e in p.get("errors", []) if isinstance(e, dict))
    assert not out.exists()


def test_patch_disk_tr1_missing_radius(tmp_path):
    inp = tmp_path / "A.txt"; inp.write_text("nps 100\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    r = _run("patch-deck", "--input", str(inp), "--output", str(out),
             "--source-strategy", "disk_tr1", "--source-position", "0", "0", "10", "--source-energy", "0.662")
    assert r.returncode != 0; p = json.loads(r.stdout); assert p["ok"] is False
    assert any(e.get("code") == "MISSING_SOURCE_RADIUS" for e in p.get("errors", []) if isinstance(e, dict))
    assert not out.exists()


def test_prepare_disk_tr1_dry(tmp_path):
    inp = tmp_path / "A.txt"; inp.write_text("f8:p,e 1\nnps 100000\n", encoding="utf-8")
    r = _run("prepare-workflow", "--input", str(inp), "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "patch-and-run", "--source-strategy", "disk_tr1",
             "--source-position", "0", "0", "10", "--source-radius", "0.15", "--source-energy", "0.662")
    assert r.returncode == 0; p = json.loads(r.stdout); assert p["ok"]
    assert (tmp_path / "w" / "A.txt").exists()
    assert (tmp_path / "w" / "manifest.json").exists()


def test_run_workflow_disk_tr1_dry(tmp_path):
    inp = tmp_path / "A.txt"; inp.write_text("f8:p,e 1\nnps 100000\n", encoding="utf-8")
    r = _run("run-workflow", "--input", str(inp), "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "patch-and-run", "--source-strategy", "disk_tr1",
             "--source-position", "0", "0", "10", "--source-radius", "0.15", "--source-energy", "0.662", "--dry-run")
    assert r.returncode == 0; p = json.loads(r.stdout); assert p["ok"]
    assert p["dry_run"] is True; assert p["executed"] is False


# ---- prepare-workflow ----
def test_prepare_patch_nps_dry(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nnps 100000\n",encoding="utf-8")
    r=_run("prepare-workflow","--input",str(inp),"--work-dir",str(tmp_path/"w"),
           "--workflow-mode","patch-and-run","--source-strategy","preserve_existing_source","--nps","1e7")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
    assert (tmp_path/"w"/"A.txt").exists()
    assert (tmp_path/"w"/"manifest.json").exists()

# ---- run-workflow dry-run ----
def test_run_workflow_dry(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=_run("run-workflow","--input",str(inp),"--work-dir",str(tmp_path/"w"),
           "--workflow-mode","run-only","--dry-run")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
    assert p["dry_run"]==True; assert p["executed"]==False

# ---- batch-workflow ----
def test_batch_no_tally_run_only(tmp_path):
    (tmp_path/"A.txt").write_text(NO_TALLY,encoding="utf-8")
    r=_run("batch-workflow","--input-dir",str(tmp_path),"--work-dir",str(tmp_path/"w"),
           "--workflow-mode","run-only","--postprocess","none")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]

# ---- prepare-point-sweep ----
def test_prepare_point_sweep_10_25_5(tmp_path):
    (tmp_path/"A.txt").write_text("f8:p,e 1\nsdef old\nnps 100000\n",encoding="utf-8")
    r=_run("prepare-point-sweep","--input",str(tmp_path/"A.txt"),"--work-dir",str(tmp_path/"w"),
           "--start","10","--stop","25","--step","5","--source-energy","0.662","--nps","1e7")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
    assert p["prepared_count"]==4
    assert (tmp_path/"w"/"d10"/"A.txt").exists()
    assert (tmp_path/"w"/"d25"/"A.txt").exists()
    assert (tmp_path/"w"/"sweep_manifest.json").exists()
    text=(tmp_path/"w"/"d10"/"A.txt").read_text(encoding="utf-8")
    assert "sdef pos=0 0 10 par=2 erg=0.662" in text
    assert "nps 10000000" in text

# ---- run-point-sweep ----
def test_run_point_sweep_dry(tmp_path):
    (tmp_path/"A.txt").write_text("f8:p,e 1\nsdef old\nnps 100000\n",encoding="utf-8")
    r=_run("run-point-sweep","--input",str(tmp_path/"A.txt"),"--work-dir",str(tmp_path/"w"),
           "--distances","10","20","--source-energy","0.662","--dry-run")
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
    assert p["dry_run"]==True; assert p["executed"]==False
    assert "d10_A.txt" in p["runner_input_files"]

def test_run_point_sweep_invalid_range(tmp_path):
    (tmp_path/"A.txt").write_text("f8:p,e 1\nnps 100\n",encoding="utf-8")
    r=_run("run-point-sweep","--input",str(tmp_path/"A.txt"),"--work-dir",str(tmp_path/"w"),
           "--start","10","--stop","5","--step","5","--source-energy","0.662","--dry-run")
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False
    assert any(e.get("code")=="INVALID_SWEEP_RANGE" for e in p.get("errors",[]) if isinstance(e,dict))

# ---- postprocess-workflow ----
def test_postprocess_f4_blocked(tmp_path):
    (tmp_path/"A.txt").write_text(F4,encoding="utf-8")
    r=_run("postprocess-workflow","--input",str(tmp_path/"A.txt"),"--work-dir",str(tmp_path/"w"),
           "--mode","csv","--mcnp-output",str(tmp_path/"out.txt"))
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False
    assert any(b.get("code")=="CSV_REQUIRES_F8" for b in p.get("blocked",[]))

def test_postprocess_missing_output(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=_run("postprocess-workflow","--input",str(tmp_path/"A.txt"),"--work-dir",str(tmp_path/"w"),
           "--mode","csv","--mcnp-output",str(tmp_path/"nope.txt"))
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False
    assert any(e.get("code")=="MISSING_MCNP_OUTPUT" for e in p.get("errors",[]) if isinstance(e,dict))
