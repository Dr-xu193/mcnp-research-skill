"""Tests for point-source sweep preparation."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from mcnp_research_skill.workflow.sweep import prepare_disk_sweep, prepare_point_sweep, run_point_sweep

def deck(*lines): return "\n".join(lines) + "\n"
F8 = deck("test","sdef old source","f8:p,e 1","nps 100000")

# ---- distance expansion ----
def test_start_stop_step_inclusive():
    r=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),start=10,stop=25,step=5,source_energy=0.662)
    assert r["distances"]==[10,15,20,25]

def test_explicit_distances_priority():
    r=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),distances=[3,7],start=10,stop=25,step=5,source_energy=0.662)
    assert r["distances"]==[3,7]

# ---- position computation ----
def test_axis_z_positive(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],axis="z",reference_position=(0,0,5),direction=-1,source_energy=0.662)
    assert r["ok"]; assert r["items"][0]["source_position"]==[0,0,-5]

def test_axis_x_y_works(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[5],axis="x",direction=1,source_energy=0.662)
    assert r["items"][0]["source_position"]==[5,0,0]
    r2=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w2",distances=[5],axis="y",direction=1,source_energy=0.662)
    assert r2["items"][0]["source_position"]==[0,5,0]

# ---- multiple distances generate prepared inputs ----
def test_multiple_distances(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,20],axis="z",source_energy=0.662)
    assert r["ok"]; assert r["prepared_count"]==2
    for item in r["items"]:
        text=Path(item["prepared_input_path"]).read_text(encoding="utf-8")
        assert "sdef pos=" in text; assert "par=2" in text; assert "erg=0.662" in text

# ---- nps patch ----
def test_nps_sweep(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,nps="1e7")
    assert r["ok"]
    text=Path(r["items"][0]["prepared_input_path"]).read_text(encoding="utf-8")
    assert "nps 10000000" in text

# ---- SI/SP/TR preserved ----
def test_sweep_preserves_si_sp_tr(tmp_path):
    d=deck("test","sdef old","si1 0 0.15","sp1 -21 1","TR1 0 0 -16","f8:p,e 1","nps 100")
    inp=tmp_path/"A.txt"; inp.write_text(d,encoding="utf-8")
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662)
    assert r["ok"]
    text=Path(r["items"][0]["prepared_input_path"]).read_text(encoding="utf-8")
    assert "si1 0 0.15" in text; assert "sp1 -21 1" in text; assert "TR1 0 0 -16" in text

# ---- validation ----
def test_missing_source_energy():
    r=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),distances=[10],source_energy="")
    assert r["ok"]==False
    assert any(e.get("code")=="MISSING_SOURCE_ENERGY" for e in r["errors"] if isinstance(e,dict))

def test_invalid_axis():
    r=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),distances=[10],axis="q",source_energy=0.662)
    assert r["ok"]==False
    assert any(e.get("code")=="INVALID_SWEEP_AXIS" for e in r["errors"] if isinstance(e,dict))

def test_invalid_range():
    r=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),start=10,stop=5,step=5,source_energy=0.662)
    assert r["ok"]==False
    assert any(e.get("code")=="INVALID_SWEEP_RANGE" for e in r["errors"] if isinstance(e,dict))
    r2=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),start=5,stop=10,step=0,source_energy=0.662)
    assert r2["ok"]==False
    assert any(e.get("code")=="INVALID_SWEEP_RANGE" for e in r2["errors"] if isinstance(e,dict))

def test_invalid_reference():
    r=prepare_point_sweep(input_path=Path("."),work_dir=Path("w"),distances=[10],reference_position=(0,0),source_energy=0.662)
    assert r["ok"]==False
    assert any(e.get("code")=="INVALID_REFERENCE_POSITION" for e in r["errors"] if isinstance(e,dict))

def test_input_file_not_found():
    r=prepare_point_sweep(input_path=Path("/nonexistent/A.txt"),work_dir=Path("w"),distances=[10],source_energy=0.662)
    assert r["ok"]==False
    assert any(e.get("code")=="INPUT_FILE_NOT_FOUND" for e in r["errors"] if isinstance(e,dict))

# ---- partial / all failure ----
def test_partial_failure(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    calls=[0]
    def fake_prep(**kw):
        calls[0]+=1; ok=calls[0]==1
        return {"ok":ok,"prepared_input_path":f"p{calls[0]}.txt","blocked":[],"errors":[] if ok else ["string err"],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.prepare_workflow",fake_prep)
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,20],source_energy=0.662)
    assert r["ok"]; assert r["prepared_count"]==1; assert r["failed_count"]==1
    failed=[i for i in r["items"] if not i["ok"]][0]
    assert isinstance(failed["errors"][0],dict)
    assert failed["errors"][0].get("code")=="PREPARE_FAILED"

def test_all_failure(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    def fake_prep(**kw): return {"ok":False,"prepared_input_path":"","blocked":[],"errors":["fail"],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.prepare_workflow",fake_prep)
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,20],source_energy=0.662)
    assert r["ok"]==False
    assert any(e.get("code")=="SWEEP_ALL_FAILED" for e in r["errors"] if isinstance(e,dict))
    # Per-item errors also structured
    for item in r["items"]:
        assert isinstance(item["errors"][0],dict)
        assert item["errors"][0].get("code")=="PREPARE_FAILED"

# ---- sweep manifest ----
def test_sweep_manifest_written(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=prepare_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662)
    assert (tmp_path/"w"/"sweep_manifest.json").exists()

# ---- CLI ----
def test_cli_sweep_ok(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","prepare-point-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),
        "--distances","10","20","--source-energy","0.662"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]; assert p["prepared_count"]==2

def test_cli_sweep_input_not_found(tmp_path):
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","prepare-point-sweep",
        "--input",str(tmp_path/"nope.txt"),"--work-dir",str(tmp_path/"w"),
        "--distances","10","--source-energy","0.662"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False

def test_cli_sweep_invalid_range(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","prepare-point-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),
        "--start","10","--stop","5","--step","5","--source-energy","0.662"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False
    assert any(e.get("code")=="INVALID_SWEEP_RANGE" for e in p["errors"] if isinstance(e,dict))


# ---- run_point_sweep ----

def test_run_sweep_dry_run(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,15],source_energy=0.662,execute=False)
    assert r["ok"]; assert r["dry_run"]==True; assert r["executed"]==False
    assert r["run"]["status"]=="skipped_dry_run"
    assert r["runner_input_files"]==["d10_A.txt","d15_A.txt"]

def test_run_sweep_execute_no_confirm(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,execute=True,confirm_mpi=False)
    assert r["ok"]==False
    assert any(e.get("code")=="MISSING_CONFIRM_MPI" for e in r["errors"] if isinstance(e,dict))

def test_run_sweep_execute_no_mpi_config(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,execute=True,confirm_mpi=True,mpi_config_path=None)
    assert r["ok"]==False
    assert any(e.get("code")=="MISSING_MPI_CONFIG" for e in r["errors"] if isinstance(e,dict))

def test_run_sweep_prepare_all_failed_no_runner(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    def fail_prep(**kw): return {"ok":False,"prepared_count":0,"items":[{"ok":False,"distance":10}],"errors":[{"code":"X"}],"warnings":[],"artifacts":{}}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.prepare_point_sweep",fail_prep)
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,execute=True,confirm_mpi=True,mpi_config_path="cfg")
    assert r["ok"]==False

def test_run_sweep_execute_mock_runner(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    calls=[]
    def fake_runner(**kw): calls.append(kw); return {"ok":True,"commands":[],"completed":[],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.run_mpi_batch",fake_runner)
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,15],source_energy=0.662,execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]; assert r["executed"]==True
    assert len(calls)==1; assert calls[0]["input_files"]==["d10_A.txt","d15_A.txt"]

def test_run_sweep_runner_exception(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def crash(**kw): raise RuntimeError("boom")
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.run_mpi_batch",crash)
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]==False; assert r["run"]["status"]=="failed"
    assert any(e.get("code")=="RUNNER_FAILED" for e in r["errors"] if isinstance(e,dict))

def test_run_sweep_dry_run_postprocess_planned(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,postprocess="csv",execute=False)
    assert r["ok"]; assert r["postprocess_status"]=="planned_not_executed"

def test_run_sweep_postprocess_mock(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake_runner(**kw): return {"ok":True,"commands":[],"completed":[],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.run_mpi_batch",fake_runner)
    pp_calls=[]
    def fake_pp(**kw): pp_calls.append(kw); return {"ok":True,"artifacts":{"csv":"c.csv"},"blocked":[],"errors":[],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.postprocess_workflow",fake_pp)
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,15],source_energy=0.662,postprocess="csv",execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]; assert len(pp_calls)==2

def test_run_sweep_postprocess_partial_failure(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake_runner(**kw): return {"ok":True,"commands":[],"completed":[],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.run_mpi_batch",fake_runner)
    cc=[0]
    def fake_pp(**kw): cc[0]+=1; ok=cc[0]==1; return {"ok":ok,"artifacts":{},"blocked":[],"errors":[] if ok else ["fail"],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.postprocess_workflow",fake_pp)
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10,15],source_energy=0.662,postprocess="csv",execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]; assert r["postprocess_summary"]["succeeded"]==1; assert r["postprocess_summary"]["failed"]==1

def test_run_sweep_postprocess_all_failed(tmp_path,monkeypatch):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    cfg=tmp_path/"cfg.yaml"; cfg.write_text('mpi_command: "echo"\n',encoding="utf-8")
    def fake_runner(**kw): return {"ok":True,"commands":[],"completed":[],"failed":[],"warnings":[],"errors":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.run_mpi_batch",fake_runner)
    def fake_pp(**kw): return {"ok":False,"artifacts":{},"blocked":[],"errors":["fail"],"warnings":[]}
    monkeypatch.setattr("mcnp_research_skill.workflow.sweep.postprocess_workflow",fake_pp)
    r=run_point_sweep(input_path=inp,work_dir=tmp_path/"w",distances=[10],source_energy=0.662,postprocess="csv",execute=True,confirm_mpi=True,mpi_config_path=str(cfg))
    assert r["ok"]==False
    assert any(e.get("code")=="POSTPROCESS_ALL_FAILED" for e in r["errors"] if isinstance(e,dict))

# ---- CLI run-point-sweep ----
def test_cli_run_sweep_dry_run(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","run-point-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),
        "--distances","10","20","--source-energy","0.662","--dry-run"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]; assert p["dry_run"]==True

def test_cli_run_sweep_execute_no_confirm(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","run-point-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),
        "--distances","10","--source-energy","0.662","--execute"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode!=0; p=json.loads(r.stdout)
    assert any("MISSING_CONFIRM_MPI" in str(e) for e in p.get("errors",[]))

def test_cli_run_sweep_invalid_range(tmp_path):
    inp=tmp_path/"A.txt"; inp.write_text(F8,encoding="utf-8")
    r=subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","run-point-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),
        "--start","10","--stop","5","--step","5","--source-energy","0.662","--dry-run"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode!=0; p=json.loads(r.stdout); assert p["ok"]==False
    assert any(e.get("code")=="INVALID_SWEEP_RANGE" for e in p["errors"] if isinstance(e,dict))


# ---- prepare_disk_sweep ----

def test_prepare_disk_sweep_distances(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nsdef old\nnps 100000\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", distances=[10, 20], source_energy=0.662, source_radius=0.15)
    assert r["ok"]; assert r["prepared_count"]==2

def test_prepare_disk_sweep_start_stop_step(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nsdef old\nnps 100\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", start=10, stop=25, step=5, source_energy=0.662, source_radius=0.15)
    assert r["ok"]; assert r["distances"]==[10,15,20,25]

def test_prepare_disk_sweep_generates_disk_tr1_cards(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nsdef old\nnps 100000\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", distances=[10], source_energy=0.662, source_radius=0.15)
    text = Path(r["items"][0]["prepared_input_path"]).read_text(encoding="utf-8")
    assert "sdef pos=0 0 0 rad=" in text; assert "tr=" in text; assert "si" in text; assert "sp" in text

def test_prepare_disk_sweep_auto_card_id(tmp_path):
    inp = tmp_path/"A.txt"
    inp.write_text("f8:p,e 1\nsdef old\nsi1 0 0.15\nsp1 -21 1\nTR1 0 0 -16\nnps 100\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", distances=[10], source_energy=0.662, source_radius=0.15)
    text = Path(r["items"][0]["prepared_input_path"]).read_text(encoding="utf-8")
    assert "tr2" in text or "tr3" in text

def test_prepare_disk_sweep_missing_radius(tmp_path):
    r = prepare_disk_sweep(input_path=Path("."), work_dir=Path("w"), distances=[10], source_energy=0.662, source_radius="")
    assert r["ok"]==False
    assert any(e.get("code")=="MISSING_SOURCE_RADIUS" for e in r["errors"] if isinstance(e,dict))

def test_prepare_disk_sweep_card_id_conflict(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("tr7 1 2 3\nf8:p,e 1\nnps 100\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", distances=[10], source_energy=0.662, source_radius=0.15, source_card_id=7)
    assert r["ok"] or any(item["ok"]==False for item in r["items"])

def test_prepare_disk_sweep_with_nps(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nnps 100000\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", distances=[10], source_energy=0.662, source_radius=0.15, nps="1e7")
    text = Path(r["items"][0]["prepared_input_path"]).read_text(encoding="utf-8")
    assert "nps 10000000" in text

def test_prepare_disk_sweep_no_runner(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nsdef old\nnps 100\n", encoding="utf-8")
    r = prepare_disk_sweep(input_path=inp, work_dir=tmp_path/"w", distances=[10], source_energy=0.662, source_radius=0.15)
    assert r["ok"]

# CLI
def test_cli_prepare_disk_sweep_ok(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nsdef old\nnps 100\n", encoding="utf-8")
    r = subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","prepare-disk-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),"--distances","10","20",
        "--source-energy","0.662","--source-radius","0.15"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode==0; p=json.loads(r.stdout); assert p["ok"]; assert p["prepared_count"]==2

def test_cli_prepare_disk_sweep_missing_radius(tmp_path):
    inp = tmp_path/"A.txt"; inp.write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")
    r = subprocess.run([sys.executable,"-m","mcnp_research_skill.cli","prepare-disk-sweep",
        "--input",str(inp),"--work-dir",str(tmp_path/"w"),"--distances","10",
        "--source-energy","0.662","--source-radius","-1"],
        cwd=Path.cwd(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    p=json.loads(r.stdout); assert p["ok"]==False
