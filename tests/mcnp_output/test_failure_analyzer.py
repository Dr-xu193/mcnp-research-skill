"""Tests for MCNP5 front-of-output failure analyzer."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]


def _run(*args):
    return subprocess.run(
        CLI + list(args), text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


# ==================================================================
# Front matter fatal error
# ==================================================================

def test_front_300_fatal_error():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    lines = ["header\n"] * 119 + ["fatal error in input\n"] + ["rest\n"] * 880
    output = "".join(lines)
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert result["status"] == "failed"
    assert any(f["code"] == "MCNP_FATAL_ERROR" for f in result["findings"])
    assert result["front_lines_analyzed"] == 300
    assert result["total_output_lines"] == 1000


def test_front_warning():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = ("header\n" * 50) + "warning: unused variable\n" + ("ok\n" * 200)
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_WARNING" for f in result["findings"])


# ==================================================================
# Input format
# ==================================================================

def test_line_too_long():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 50 + "error: line too long in input card\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_LINE_TOO_LONG" for f in result["findings"])
    assert any("diagnose" in s["action"] for s in result["suggestions"])


def test_bad_continuation():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 30 + "bad continuation detected\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_BAD_CONTINUATION" for f in result["findings"])


# ==================================================================
# Geometry
# ==================================================================

def test_unknown_surface():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 80 + "fatal error: undefined surface 25\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_UNKNOWN_SURFACE" for f in result["findings"])
    assert any("cell" in s["message"].lower() or "surface" in s["message"].lower()
               for s in result["suggestions"])


def test_unknown_cell():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 60 + "error: cell not found 999\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_UNKNOWN_CELL" for f in result["findings"])


# ==================================================================
# Material / xsdir
# ==================================================================

def test_xs_library_not_found():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 40 + "error: xsdir library not found\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_XS_LIBRARY_NOT_FOUND" for f in result["findings"])
    # Must not suggest download/piracy
    for s in result["suggestions"]:
        assert "download" not in s["message"].lower()


# ==================================================================
# Source / SDEF
# ==================================================================

def test_source_error_with_disk_tr1_context():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 70 + "bad source distribution error\n"
    context = {
        "source_strategy": "disk_tr1",
        "source_radius": 0.15,
        "model": "nai_2x2_template",
    }
    result = analyze_mcnp_failure(output_text=output, front_lines=300, context=context)
    assert any(f["code"] in ("MCNP_SOURCE_DISTRIBUTION_ERROR", "MCNP_SOURCE_ERROR")
               for f in result["findings"])
    assert any("disk_tr1" in s["message"].lower() for s in result["suggestions"])


# ==================================================================
# Tally
# ==================================================================

def test_tally_error_with_csv_postprocess():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 60 + "bad tally F4\n"
    context = {"postprocess": "csv"}
    result = analyze_mcnp_failure(output_text=output, front_lines=300, context=context)
    assert any(f["code"] == "MCNP_TALLY_ERROR" for f in result["findings"])


# ==================================================================
# Mode mismatch
# ==================================================================

def test_mode_particle_mismatch():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 55 + "error: source particle not in mode\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert any(f["code"] == "MCNP_MODE_PARTICLE_MISMATCH" for f in result["findings"])


# ==================================================================
# Runtime / stderr
# ==================================================================

def test_mpi_not_found_stderr():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    result = analyze_mcnp_failure(
        output_text="header\n",
        stderr_text="mpirun: command not found\n",
        returncode=127,
        front_lines=300,
    )
    assert result["fallback_used"]
    assert any(f["code"] == "MPI_LAUNCHER_NOT_FOUND" for f in result["findings"])


def test_mcnp_exe_not_found_stderr():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    result = analyze_mcnp_failure(
        output_text="header\n",
        stderr_text="mcnp5mpi.exe: command not found\n",
        returncode=127,
        front_lines=300,
    )
    assert any(f["code"] == "MCNP_EXECUTABLE_NOT_FOUND" for f in result["findings"])


def test_permission_denied_stderr():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    result = analyze_mcnp_failure(
        output_text="header\n",
        stderr_text="permission denied\n",
        returncode=1,
        front_lines=300,
    )
    assert any(f["code"] == "RUNTIME_PERMISSION_DENIED" for f in result["findings"])


# ==================================================================
# Normal completion
# ==================================================================

def test_normal_termination():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "header\n" * 50 + "normal termination\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert result["status"] == "completed"


# ==================================================================
# Fallback: no findings in front, error in tail
# ==================================================================

def test_fallback_tail():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    # Clean front 300 lines, error at line 500
    output = ("clean\n" * 299) + ("more clean\n" * 200) + "fatal error at end\n"
    result = analyze_mcnp_failure(output_text=output, returncode=1, front_lines=300)
    assert result["fallback_used"]


# ==================================================================
# Huge output safety
# ==================================================================

def test_huge_output_token_safety():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = ("line\n" * 19999) + "fatal error\n"
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert result["total_output_lines"] == 20000
    assert result["front_lines_analyzed"] == 300
    # Findings should be empty (error at line 20000, beyond front 300)
    assert not result["findings"]


def test_user_output_not_contain_full_log():
    from mcnp_research_skill.mcnp_output.failure_analyzer import (
        analyze_mcnp_failure,
        render_failure_response,
    )
    output = ("header\n" * 119) + "fatal error\n" + ("more\n" * 5000)
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    text = render_failure_response(result)
    # Must be under 10K chars (reasonable for user display)
    assert len(text) < 10000
    assert "fatal" in text.lower() or "致命" in text


# ==================================================================
# Default text / --json
# ==================================================================

def test_analyze_cli_default_chinese(tmp_path):
    output = "header\n" * 50 + "fatal error\n"
    (tmp_path / "o.txt").write_text(output, encoding="utf-8")
    r = _run("analyze-run-failure", "--output", str(tmp_path / "o.txt"))
    assert not r.stdout.strip().startswith("{")
    assert any(ord(c) > 127 for c in r.stdout)


def test_analyze_cli_json(tmp_path):
    output = "header\n" * 50 + "fatal error\n"
    (tmp_path / "o.txt").write_text(output, encoding="utf-8")
    r = _run("--json", "analyze-run-failure", "--output", str(tmp_path / "o.txt"))
    assert r.stdout.strip().startswith("{")
    d = json.loads(r.stdout)
    assert d["status"] == "failed"


# ==================================================================
# Context file
# ==================================================================

def test_analyze_with_context_file(tmp_path):
    output = "header\n" * 80 + "bad source error\n"
    (tmp_path / "o.txt").write_text(output, encoding="utf-8")
    context = {"source_strategy": "disk_tr1", "model": "nai_2x2_template"}
    (tmp_path / "ctx.json").write_text(json.dumps(context), encoding="utf-8")

    r = _run("--json", "analyze-run-failure", "--output", str(tmp_path / "o.txt"),
             "--context", str(tmp_path / "ctx.json"))
    d = json.loads(r.stdout)
    assert d["context"]["source_strategy"] == "disk_tr1"


# ==================================================================
# Version detection
# ==================================================================

def test_mcnp_version_detection():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    output = "Thread Name & Version = MCNP5_RSICC, 1.14\n" + ("ok\n" * 100)
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    assert result.get("mcnp_version_detected") is not None


# ==================================================================
# Findings are deduplicated
# ==================================================================

def test_findings_deduplicated():
    from mcnp_research_skill.mcnp_output.failure_analyzer import analyze_mcnp_failure

    # Multiple "fatal error" lines
    output = "fatal error\n" * 10
    result = analyze_mcnp_failure(output_text=output, front_lines=300)
    fatal_count = sum(1 for f in result["findings"] if f["code"] == "MCNP_FATAL_ERROR")
    assert fatal_count == 1
