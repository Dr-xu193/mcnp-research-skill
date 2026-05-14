"""Tests for point-source sweep preparation."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from mcnp_research_skill.workflow.sweep import prepare_point_sweep

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
