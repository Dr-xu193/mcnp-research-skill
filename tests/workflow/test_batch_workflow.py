"""Tests for batch workflow."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from mcnp_research_skill.workflow.batch import batch_workflow

def deck(*lines): return "\n".join(lines) + "\n"

F8 = deck("test","sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.662","si1 0 0.15","sp1 -21 1","TR1 0 0 -16.1900","f8:p,e 1","nps 100000")
F4 = deck("test","f4:n 1","nps 100")
NO_TALLY = deck("test","nps 100")

# ---- scan *.txt ----
def test_scan_txt_sorted(tmp_path):
    (tmp_path / "B.txt").write_text(F8,encoding="utf-8")
    (tmp_path / "A.txt").write_text(F8,encoding="utf-8")
    (tmp_path / "notes.md").write_text("docs",encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only")
    assert r["ok"]; assert r["total_files"]==2
    assert [p["input_file"] for p in r["per_file_results"]]==["A.txt","B.txt"]

# ---- input_files explicit ----
def test_input_files_explicit(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"B.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"C.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",input_files=["A.txt","C.txt"])
    assert r["total_files"]==2
    assert [p["input_file"] for p in r["per_file_results"]]==["A.txt","C.txt"]

# ---- run-only + F4 + postprocess none -> ok ----
def test_run_only_f4_ok(tmp_path):
    (tmp_path/"deck.txt").write_text(F4,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="none")
    assert r["ok"]; assert r["prepared_count"]==1

# ---- run-only + no tally + postprocess none -> ok ----
def test_run_only_no_tally_ok(tmp_path):
    (tmp_path/"deck.txt").write_text(NO_TALLY,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="none")
    assert r["ok"]; assert r["prepared_count"]==1

# ---- nps batch patch ----
def test_nps_batch_patch(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"B.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="patch-and-run",source_strategy="preserve_existing_source",nps="1e7")
    assert r["ok"]; assert r["prepared_count"]==2
    for e in r["per_file_results"]:
        text=Path(e["prepared_input_path"]).read_text(encoding="utf-8")
        assert "nps 10000000" in text
        assert "sdef pos" in text; assert "si1 0" in text; assert "TR1 0" in text

# ---- postprocess=csv + F4 blocked, F8 still ok ----
def test_mixed_f8_f4_postprocess_csv(tmp_path):
    (tmp_path/"good.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"bad.txt").write_text(F4,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="csv")
    assert r["ok"]  # at least one ok
    assert r["prepared_count"]==1; assert r["blocked_count"]==1
    good=[e for e in r["per_file_results"] if e["ok"]]
    bad=[e for e in r["per_file_results"] if not e["ok"]]
    assert good[0]["input_file"]=="good.txt"
    assert bad[0]["input_file"]=="bad.txt"
    assert any("CSV_REQUIRES_F8" in str(b) for b in bad[0]["blocked"])

# ---- all blocked -> ok=false ----
def test_all_blocked(tmp_path):
    (tmp_path/"a.txt").write_text(F4,encoding="utf-8")
    (tmp_path/"b.txt").write_text(F4,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="csv")
    assert r["ok"]==False; assert r["prepared_count"]==0

# ---- input_dir not found ----
def test_input_dir_not_found(tmp_path):
    r=batch_workflow(input_dir=tmp_path/"nope",work_dir=tmp_path/"w",workflow_mode="run-only")
    assert r["ok"]==False
    assert any(e.get("code")=="INPUT_DIR_NOT_FOUND" for e in r["errors"] if isinstance(e,dict))

# ---- no txt files ----
def test_no_txt_files(tmp_path):
    d=tmp_path/"empty"; d.mkdir()
    r=batch_workflow(input_dir=d,work_dir=tmp_path/"w",workflow_mode="run-only")
    assert r["ok"]==False
    assert any(e.get("code")=="NO_INPUT_FILES" for e in r["errors"] if isinstance(e,dict))

# ---- dry-run no runner ----
def test_dry_run_no_runner(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",execute=False)
    assert r["ok"]; assert r["dry_run"]==True; assert r["run"]["status"]=="skipped_dry_run"

# ---- execute no confirm ----
def test_execute_no_confirm(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",execute=True,confirm_mpi=False)
    assert r["ok"]==False
    assert any(e.get("code")=="MISSING_CONFIRM_MPI" for e in r["errors"] if isinstance(e,dict))

# ---- execute + confirm no mpi-config ----
def test_execute_no_mpi_config(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",execute=True,confirm_mpi=True,mpi_config_path=None)
    assert r["ok"]==False
    assert any(e.get("code")=="MISSING_MPI_CONFIG" for e in r["errors"] if isinstance(e,dict))

# ---- execute + mock runner ----
def test_execute_mock_runner(tmp_path,monkeypatch):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"B.txt").write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    calls=[]
    def fake(**kw): calls.append(kw); return {"ok":True,"commands":[],"completed":[],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.run_mpi_batch",fake)
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",
                      execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]; assert r["executed"]==True
    assert len(calls)==1
    assert calls[0]["input_files"]==["A.txt","B.txt"]

# ---- runner exception ----
def test_runner_exception(tmp_path,monkeypatch):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def crash(**kw): raise RuntimeError("boom")
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.run_mpi_batch",crash)
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",
                      execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]==False; assert r["run"]["status"]=="failed"
    assert any(e.get("code")=="RUNNER_FAILED" for e in r["errors"] if isinstance(e,dict))

# ---- batch_manifest written ----
def test_batch_manifest_written(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only")
    assert (tmp_path/"w"/"batch_manifest.json").exists()

# ---- name collision handled ----
def test_stem_collision(tmp_path):
    (tmp_path/"deck.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only")
    # subdir should be "deck" (stem of deck.txt)
    assert (tmp_path/"w"/"deck"/"deck.txt").exists()
    used_stems={p.name for p in (tmp_path/"w").iterdir() if p.is_dir()}
    assert "deck" in used_stems

# ---- CLI dry-run ----
def test_cli_batch_dry_run(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","batch-workflow",
        "--input-dir",str(tmp_path),"--work-dir",str(tmp_path/"w"),
        "--workflow-mode","run-only","--dry-run"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]==True

# ---- CLI input dir not found ----
def test_cli_batch_input_not_found(tmp_path):
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","batch-workflow",
        "--input-dir",str(tmp_path/"nope"),"--work-dir",str(tmp_path/"w"),
        "--workflow-mode","run-only"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False

# ---- CLI execute no confirm ----
def test_cli_batch_execute_no_confirm(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","batch-workflow",
        "--input-dir",str(tmp_path),"--work-dir",str(tmp_path/"w"),
        "--workflow-mode","run-only","--execute"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode!=0; p=json.loads(r.stdout)
    assert any("MISSING_CONFIRM_MPI" in str(e) for e in p.get("errors",[]))

# ---- CLI execute + mock runner ----
def test_cli_batch_mock_runner(tmp_path,monkeypatch):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake(**kw): return {"ok":True,"commands":[],"completed":[],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.run_mpi_batch",fake)
    from mcnp_research_skill.cli import main
    r=main(["batch-workflow","--input-dir",str(tmp_path),"--work-dir",str(tmp_path/"w"),
            "--workflow-mode","run-only","--execute","--confirm-mpi","--mpi-config",str(cfg)])
    assert r["ok"]==True; assert r["executed"]==True


# ---- postprocess wiring ----

def test_batch_dry_run_postprocess_planned(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="csv",execute=False)
    assert r["ok"]; assert r.get("postprocess_status","planned_not_executed")=="planned_not_executed"

def test_batch_execute_calls_postprocess_per_file(tmp_path,monkeypatch):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"B.txt").write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake_runner(**kw):
        return {"ok":True,"commands":[],"completed":[{"output_path":str(tmp_path/"A.out")},{"output_path":str(tmp_path/"B.out")}],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.run_mpi_batch",fake_runner)
    pp_calls=[]
    def fake_pp(**kw):
        pp_calls.append(kw)
        return {"ok":True,"artifacts":{"csv":"c.csv"},"blocked":[],"errors":[],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.postprocess_workflow",fake_pp)
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="csv",
                      execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]; assert len(pp_calls)==2
    assert pp_calls[0]["mcnp_output_path"]==str(tmp_path/"A.out")

def test_batch_partial_postprocess_failure(tmp_path,monkeypatch):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    (tmp_path/"B.txt").write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake_runner(**kw):
        return {"ok":True,"commands":[],"completed":[{"output_path":"a.out"},{"output_path":"b.out"}],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.run_mpi_batch",fake_runner)
    call_count=[0]
    def fake_pp(**kw):
        call_count[0]+=1
        ok=call_count[0]==1  # first succeeds, second fails
        return {"ok":ok,"artifacts":{},"blocked":[],"errors":[] if ok else ["pp fail"],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.postprocess_workflow",fake_pp)
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="csv",
                      execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]  # partial failure still ok
    assert r["postprocess_summary"]["succeeded"]==1; assert r["postprocess_summary"]["failed"]==1

def test_batch_all_postprocess_failure(tmp_path,monkeypatch):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake_runner(**kw):
        return {"ok":True,"commands":[],"completed":[{"output_path":"a.out"}],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.run_mpi_batch",fake_runner)
    def fake_pp(**kw): return {"ok":False,"artifacts":{},"blocked":[],"errors":["pp fail"],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.batch.postprocess_workflow",fake_pp)
    r=batch_workflow(input_dir=tmp_path,work_dir=tmp_path/"w",workflow_mode="run-only",postprocess="csv",
                      execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]==False
    assert any(e.get("code")=="POSTPROCESS_ALL_FAILED" for e in r["errors"] if isinstance(e,dict))

def test_cli_batch_mcnp_outputs_arg(tmp_path):
    (tmp_path/"A.txt").write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","batch-workflow",
        "--input-dir",str(tmp_path),"--work-dir",str(tmp_path/"w"),
        "--workflow-mode","run-only","--postprocess","csv","--dry-run",
        "--mcnp-outputs","a.out","b.out"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]
