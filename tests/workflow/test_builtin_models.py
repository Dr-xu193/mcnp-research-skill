"""Tests for built-in verified MCNP deck models."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "mcnp_research_skill.cli"]
ROOT = Path.cwd()

FIXTURE = (
    Path(__file__).resolve().parent.parent.parent
    / "mcnp_research_skill/models/fixtures/nai_3x3_verified.txt"
)


def _run(*args, tmp_path=None):
    return subprocess.run(
        CLI + list(args),
        cwd=str(tmp_path or ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _read_fixture():
    return FIXTURE.read_text(encoding="utf-8")


def _fixture_lines():
    return _read_fixture().splitlines()


# ==================================================================
# registry boundary
# ==================================================================

def test_registry_only_has_nai_3x3_verified():
    """No 1x1, 2x2, or other unverified NaI models."""
    from mcnp_research_skill.models.registry import list_models, get_model

    models = list_models()
    ids = [m["id"] for m in models]
    assert ids == ["nai_3x3_verified"]

    # Explicitly reject any unverified NaI sizes
    for bogus in ("nai_1x1_verified", "nai_2x2_verified", "nai_1_2_inch"):
        assert get_model(bogus) is None


def test_registry_entry_has_no_reference_points():
    """Registry entry must NOT define reference_points / front_surface derived from geometry."""
    from mcnp_research_skill.models.registry import get_model

    m = get_model("nai_3x3_verified")
    assert m is not None
    assert "reference_points" not in m
    assert "front_surface" not in m
    assert "detector_front" not in m
    assert "crystal_front" not in m


def test_list_models_includes_nai_3x3_verified():
    from mcnp_research_skill.models.registry import list_models, get_model

    models = list_models()
    assert len(models) == 1
    assert models[0]["id"] == "nai_3x3_verified"
    assert "3x3" in models[0]["display_name"]
    assert "A.txt" in models[0]["source"]

    m = get_model("nai_3x3_verified")
    assert m is not None
    assert Path(m["deck_path"]).is_file()


def test_registry_rejects_unknown_model():
    from mcnp_research_skill.models.registry import get_model

    assert get_model("nonexistent") is None
    assert get_model("") is None


def test_resolve_deck_path_returns_existing_file():
    from mcnp_research_skill.models.registry import resolve_deck_path

    p = resolve_deck_path("nai_3x3_verified")
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "3x3 NaI" in text
    assert "f8:p,e 104" in text


def test_resolve_deck_path_raises_for_unknown():
    from mcnp_research_skill.models.registry import resolve_deck_path

    with pytest.raises(ValueError, match="Unknown built-in model"):
        resolve_deck_path("bogus_model")
    with pytest.raises(ValueError, match="nai_3x3_verified"):
        resolve_deck_path("bogus_model")


# ==================================================================
# MCNP5 deck hygiene
# ==================================================================

def test_fixture_max_line_length_under_80():
    """Every line in the fixture must be <= 80 columns (MCNP5 compat)."""
    lines = _fixture_lines()
    for i, line in enumerate(lines, 1):
        length = len(line.rstrip("\n"))
        assert length <= 80, f"Line {i} exceeds 80 columns ({length}): {line[:60]!r}"


def test_fixture_no_tabs():
    """Fixture must contain zero tab characters."""
    text = _read_fixture()
    assert "\t" not in text


def test_fixture_continuation_lines_valid():
    """Continuation lines (starting with 5+ spaces) must be valid MCNP5.

    Continuation lines must NOT start with C (comment) or $ (inline comment).
    The fixture uses continuation for the long cell-201 definition.
    """
    lines = _fixture_lines()
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if re.match(r"^ {5,}", stripped) and not stripped.isspace():
            content = stripped.lstrip()
            # Must not be a comment line
            assert not content.startswith("C "), f"Line {i} looks like a comment continuation"
            assert not content.startswith("c "), f"Line {i} looks like a comment continuation"
            assert not content.startswith("$"), f"Line {i} starts with inline comment"


def test_fixture_no_bare_chinese():
    """No bare Chinese characters outside valid MCNP comment cards.

    Chinese in the title card (line 1) is the only place allowed without
    an explicit C/$ prefix — the title card is always line 1 and MCNP
    treats it as a title, not executable input.
    """
    lines = _fixture_lines()
    for i, line in enumerate(lines, 1):
        has_cjk = bool(re.search(r"[一-鿿]", line))
        if has_cjk:
            # Title line is line 1 — that's the only bare-CJK line allowed
            assert i == 1, (
                f"Line {i} contains Chinese characters outside title card: {line[:60]!r}"
            )


def test_fixture_no_mcnp6_syntax():
    """Fixture must not use MCNP6-only syntax (double-ampersand continuation, etc.)."""
    text = _read_fixture()
    # No MCNP6-style continuation
    assert "&&" not in text
    # No MCNP6-only cards (mesh, embedded source, etc.)
    lower = text.lower()
    for mcnp6_kw in ("fmask", "embee", "embes", "embem", "embed"):
        assert mcnp6_kw not in lower, f"Fixture contains MCNP6-only keyword: {mcnp6_kw}"


def test_fixture_inspect_deck_reads():
    """inspect_deck_file can parse the fixture without errors."""
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file

    result = inspect_deck_file(str(FIXTURE))
    assert result["ok"] is True
    assert result["errors"] == []


# ==================================================================
# inspect built-in model
# ==================================================================

def test_inspect_nai_3x3_returns_ok():
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = inspect_deck_file(str(resolve_deck_path("nai_3x3_verified")))
    assert result["ok"] is True
    assert result["title"] == "3x3 NaI(Tl) Model with Encapsulated Source"
    assert result["nps"]["present"] is True
    assert result["nps"]["value"] == 100000.0
    assert result["mode"]["particles"] == ["p", "e"]
    assert result["source"]["has_sdef"] is True
    assert result["source"]["guess"] == "disk_or_area"
    assert result["geb"]["present"] is True


def test_inspect_nai_3x3_f8_supported():
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = inspect_deck_file(str(resolve_deck_path("nai_3x3_verified")))
    tallies = result["tallies"]
    f8s = [t for t in tallies if t["kind"] == "F8"]
    assert len(f8s) == 1
    assert f8s[0]["supported_for_csv"] is True
    assert "104" in f8s[0]["raw"]


def test_inspect_nai_3x3_geb_present_no_error():
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    result = inspect_deck_file(str(resolve_deck_path("nai_3x3_verified")))
    assert result["geb"]["present"] is True
    assert result["errors"] == []


# ==================================================================
# reference point boundary
# ==================================================================

def test_validate_reference_point_returns_structured_ok():
    """validate_reference_point must return structured dict on success."""
    from mcnp_research_skill.models.registry import validate_reference_point

    result = validate_reference_point("crystal_front_surface")
    assert result["ok"] is True
    assert result["reference_point"]["z"] == 0.0


def test_validate_reference_point_returns_structured_error():
    """validate_reference_point must return structured error for unknown names."""
    from mcnp_research_skill.models.registry import validate_reference_point

    result = validate_reference_point("front_surface")
    assert result["ok"] is False
    err = result["errors"][0]
    assert err["code"] == "UNKNOWN_REFERENCE_POINT"
    assert "front_surface" in err["message"]


def test_validate_reference_point_with_profile_rps():
    """validate_reference_point accepts optional profile reference_points."""
    from mcnp_research_skill.models.registry import validate_reference_point

    profile_rps = {
        "crystal_front": {"name": "晶体前表面", "z": 0.0, "short_label": "Front"},
    }
    result = validate_reference_point("crystal_front", reference_points=profile_rps)
    assert result["ok"] is True
    assert result["reference_point"]["z"] == 0.0


def test_front_surface_not_in_builtin_constants():
    """"front_surface" is NOT a valid built-in reference point name."""
    from mcnp_research_skill.models.registry import validate_reference_point

    result = validate_reference_point("front_surface")
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "UNKNOWN_REFERENCE_POINT"


def test_crystal_front_surface_resolves_from_builtin():
    """Built-in crystal_front_surface is a valid reference point (z=0.0)."""
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    rp = resolve_reference_point("crystal_front_surface")
    assert rp["z"] == 0.0


def test_crystal_center_resolves_from_builtin():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    rp = resolve_reference_point("crystal_center")
    assert rp["z"] == 3.81


def test_aluminum_shell_surface_resolves_from_builtin():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    rp = resolve_reference_point("aluminum_shell_surface")
    assert rp["z"] == -0.34


def test_crystal_front_resolves_from_profile():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    profile_rps = {
        "crystal_front": {"name": "晶体前表面", "z": 0.0, "short_label": "Front"},
    }
    rp = resolve_reference_point("crystal_front", reference_points=profile_rps)
    assert rp["z"] == 0.0


def test_reference_point_via_profile_short_label():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    profile_rps = {
        "crystal_front": {"name": "晶体前表面", "z": 0.0, "short_label": "Front"},
    }
    rp = resolve_reference_point("Front", reference_points=profile_rps)
    assert rp["z"] == 0.0


def test_reference_point_via_profile_name():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    profile_rps = {
        "crystal_front": {"name": "晶体前表面", "z": 0.0, "short_label": "Front"},
    }
    rp = resolve_reference_point("晶体前表面", reference_points=profile_rps)
    assert rp["z"] == 0.0


def test_nonexistent_reference_point_raises():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    with pytest.raises(ValueError, match="front_surface"):
        resolve_reference_point("front_surface")


def test_nonexistent_reference_point_with_profile_raises():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    profile_rps = {
        "crystal_front": {"name": "晶体前表面", "z": 0.0, "short_label": "Front"},
    }
    with pytest.raises(ValueError, match="bogus_point"):
        resolve_reference_point("bogus_point", reference_points=profile_rps)


def test_no_front_surface_deduced_from_model_name():
    """Model display name "3x3 NaI" must not imply any reference point."""
    from mcnp_research_skill.models.registry import get_model

    m = get_model("nai_3x3_verified")
    assert m is not None
    # The display name contains "3x3" and "NaI" — but that does NOT
    # automatically create a front_surface reference point.
    for key in m:
        if "front" in str(key).lower() or "surface" in str(key).lower():
            pytest.fail(f"Model entry implicitly defines a surface: {key}={m[key]!r}")


# ==================================================================
# prepare-workflow: preserve_existing_source
# ==================================================================

def test_prepare_preserve_copies_without_patching_source(tmp_path):
    """SDEF/SI/SP/TR/TRCL must be preserved verbatim; no warnings about unused cards."""
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    from mcnp_research_skill.models.registry import resolve_deck_path

    work = tmp_path / "w"
    result = prepare_workflow(
        input_path=str(resolve_deck_path("nai_3x3_verified")),
        work_dir=str(work),
        workflow_mode="patch-and-run",
        source_strategy="preserve_existing_source",
        postprocess="none",
    )
    assert result["ok"] is True
    assert result["changed"] is False
    # No POSSIBLE_UNUSED_SOURCE_CARDS warning for preserve strategy
    assert not any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in result.get("warnings", []))

    prepared = work / "nai_3x3_verified.txt"
    assert prepared.exists()
    text = prepared.read_text(encoding="utf-8")
    assert "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg=0.0595" in text
    assert "si1 0 0.15" in text
    assert "sp1 -21 1" in text
    assert "TR1 0 0 -10.34" in text
    assert "trcl=1" in text
    assert (work / "manifest.json").exists()


# ==================================================================
# prepare-workflow: point_sdef_pos
# ==================================================================

def test_prepare_point_sdef_pos_replaces_sdef_preserves_rest(tmp_path):
    """Only SDEF replaced; SI/SP/TR/TRCL preserved; POSSIBLE_UNUSED_SOURCE_CARDS warned."""
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    from mcnp_research_skill.models.registry import resolve_deck_path

    work = tmp_path / "w"
    result = prepare_workflow(
        input_path=str(resolve_deck_path("nai_3x3_verified")),
        work_dir=str(work),
        workflow_mode="patch-and-run",
        source_strategy="point_sdef_pos",
        source_position=(0, 0, 20),
        source_energy=0.662,
        nps="5e6",
        postprocess="none",
    )
    assert result["ok"] is True
    assert result["changed"] is True

    # POSSIBLE_UNUSED_SOURCE_CARDS must appear (old SDEF had rad=/ext=/tr=)
    assert any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in result.get("warnings", []))

    prepared = work / "nai_3x3_verified.txt"
    text = prepared.read_text(encoding="utf-8")
    assert "sdef pos=0 0 20 par=2 erg=0.662" in text
    assert "si1 0 0.15" in text
    assert "sp1 -21 1" in text
    assert "TR1 0 0 -10.34" in text
    assert "nps 5000000" in text


# ==================================================================
# prepare-workflow: disk_tr1
# ==================================================================

def test_prepare_disk_tr1_generates_new_cards_preserves_old(tmp_path):
    """New TR2/SI2/SP2 (auto id); old TR1/SI1/SP1 preserved; source_position is TR translation."""
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    from mcnp_research_skill.models.registry import resolve_deck_path

    work = tmp_path / "w"
    result = prepare_workflow(
        input_path=str(resolve_deck_path("nai_3x3_verified")),
        work_dir=str(work),
        workflow_mode="patch-and-run",
        source_strategy="disk_tr1",
        source_position=(0, 0, 15),
        source_radius=0.2,
        source_energy=0.662,
        nps="1e7",
        postprocess="none",
    )
    assert result["ok"] is True
    assert result["changed"] is True

    # POSSIBLE_UNUSED_SOURCE_CARDS must appear
    assert any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in result.get("warnings", []))

    prepared = work / "nai_3x3_verified.txt"
    text = prepared.read_text(encoding="utf-8")
    # New cards use auto id=2 (id=1 is taken)
    assert "sdef pos=0 0 0 rad=d2 ext=0 par=2 tr=2 erg=0.662" in text
    assert "tr2 0 0 15" in text
    assert "si2 0 0.2" in text
    assert "sp2 -21 1" in text
    # Old cards preserved
    assert "TR1 0 0 -10.34" in text
    assert "si1 0 0.15" in text
    assert "sp1 -21 1" in text
    assert "nps 10000000" in text
    # source_position is the TR translation (not SDEF pos)
    assert "tr2 0 0 15" in text  # translation = source_position


def test_disk_tr1_does_not_treat_tr1_as_disk_source(tmp_path):
    """Existing TR1 is a geometry transform, not a disk source definition."""
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    from mcnp_research_skill.models.registry import resolve_deck_path

    work = tmp_path / "w"
    result = prepare_workflow(
        input_path=str(resolve_deck_path("nai_3x3_verified")),
        work_dir=str(work),
        workflow_mode="patch-and-run",
        source_strategy="disk_tr1",
        source_position=(0, 0, 15),
        source_radius=0.2,
        source_energy=0.662,
        nps="1e7",
        postprocess="none",
    )
    prepared = work / "nai_3x3_verified.txt"
    text = prepared.read_text(encoding="utf-8")
    # TR1 is unchanged (geometry transform, not replaced)
    assert "TR1 0 0 -10.34" in text
    # New disk source uses its own TR2
    assert "tr2 0 0 15" in text


# ==================================================================
# plan-workflow / run-workflow with builtin
# ==================================================================

def test_plan_f8_csv_not_blocked_for_nai_3x3():
    from mcnp_research_skill.workflow.planner import plan_workflow
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.models.registry import resolve_deck_path

    inspection = inspect_deck_file(str(resolve_deck_path("nai_3x3_verified")))
    plan = plan_workflow(inspection, workflow_mode="run-only",
                         source_strategy="preserve_existing_source",
                         postprocess="csv", requested_nps=None)
    assert plan["ok"] is True
    assert not any(b.get("code") == "CSV_REQUIRES_F8" for b in plan.get("blocked", []))


def test_run_workflow_dry_with_builtin(tmp_path):
    from mcnp_research_skill.workflow.run import run_workflow
    from mcnp_research_skill.models.registry import resolve_deck_path

    work = tmp_path / "w"
    result = run_workflow(
        input_path=str(resolve_deck_path("nai_3x3_verified")),
        work_dir=str(work),
        workflow_mode="run-only",
        source_strategy="preserve_existing_source",
        postprocess="none",
        execute=False,
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["run"]["status"] == "skipped_dry_run"


def test_builtin_model_uses_full_deck_aware_workflow(tmp_path):
    """Built-in model must go through inspect → plan → prepare, not a shortcut."""
    from mcnp_research_skill.mcnp_input.inspection import inspect_deck_file
    from mcnp_research_skill.workflow.planner import plan_workflow
    from mcnp_research_skill.workflow.prepare import prepare_workflow
    from mcnp_research_skill.models.registry import resolve_deck_path

    deck = str(resolve_deck_path("nai_3x3_verified"))

    # 1. inspect
    insp = inspect_deck_file(deck)
    assert insp["ok"]
    assert insp["tallies"][0]["kind"] == "F8"

    # 2. plan
    plan = plan_workflow(insp, workflow_mode="run-only",
                         source_strategy="preserve_existing_source",
                         postprocess="none", requested_nps=None)
    assert plan["ok"]

    # 3. prepare
    work = tmp_path / "w"
    prep = prepare_workflow(input_path=deck, work_dir=str(work),
                            workflow_mode="run-only",
                            source_strategy="preserve_existing_source",
                            postprocess="none")
    assert prep["ok"]
    assert (work / "nai_3x3_verified.txt").exists()


# ==================================================================
# CLI: models list / inspect
# ==================================================================

def test_cli_models_list():
    r = _run("models", "list")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert len(p["models"]) == 1
    assert p["models"][0]["id"] == "nai_3x3_verified"


def test_cli_models_inspect():
    r = _run("models", "inspect", "nai_3x3_verified")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["title"] == "3x3 NaI(Tl) Model with Encapsulated Source"
    assert any(t["kind"] == "F8" and t["supported_for_csv"] for t in p["tallies"])


def test_cli_models_inspect_unknown():
    r = _run("models", "inspect", "no_such_model")
    assert r.returncode != 0
    p = json.loads(r.stdout)
    assert p["ok"] is False
    assert any(e.get("code") == "MODEL_NOT_FOUND" for e in p.get("errors", []) if isinstance(e, dict))


# ==================================================================
# CLI: prepare-workflow --builtin-model  (three strategies)
# ==================================================================

def test_cli_prepare_builtin_preserve(tmp_path):
    r = _run("prepare-workflow", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "patch-and-run",
             "--source-strategy", "preserve_existing_source",
             "--postprocess", "none")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["changed"] is False
    assert (tmp_path / "w" / "nai_3x3_verified.txt").exists()
    assert (tmp_path / "w" / "manifest.json").exists()
    # No POSSIBLE_UNUSED warning for preserve
    assert not any("POSSIBLE_UNUSED" in w for w in p.get("warnings", []))


def test_cli_prepare_builtin_point_sdef(tmp_path):
    r = _run("prepare-workflow", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "patch-and-run",
             "--source-strategy", "point_sdef_pos",
             "--source-position", "0", "0", "20",
             "--source-energy", "0.662",
             "--nps", "1e7",
             "--postprocess", "none")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["changed"] is True
    text = (tmp_path / "w" / "nai_3x3_verified.txt").read_text(encoding="utf-8")
    assert "sdef pos=0 0 20 par=2 erg=0.662" in text
    assert "TR1 0 0 -10.34" in text
    # Must have POSSIBLE_UNUSED_SOURCE_CARDS warning
    assert any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in p.get("warnings", []))


def test_cli_prepare_builtin_disk_tr1(tmp_path):
    r = _run("prepare-workflow", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "patch-and-run",
             "--source-strategy", "disk_tr1",
             "--source-position", "0", "0", "15",
             "--source-radius", "0.2",
             "--source-energy", "0.662",
             "--nps", "1e7",
             "--postprocess", "none")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["changed"] is True
    text = (tmp_path / "w" / "nai_3x3_verified.txt").read_text(encoding="utf-8")
    assert "tr2 0 0 15" in text
    assert "si2 0 0.2" in text
    assert "sp2 -21 1" in text
    assert "TR1 0 0 -10.34" in text
    assert any("POSSIBLE_UNUSED_SOURCE_CARDS" in w for w in p.get("warnings", []))


# ==================================================================
# CLI: inspect / plan / run --builtin-model
# ==================================================================

def test_cli_inspect_builtin():
    r = _run("inspect-deck", "--builtin-model", "nai_3x3_verified")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["title"] == "3x3 NaI(Tl) Model with Encapsulated Source"
    assert p["geb"]["present"] is True


def test_cli_plan_builtin():
    r = _run("plan-workflow", "--builtin-model", "nai_3x3_verified",
             "--workflow-mode", "run-only", "--postprocess", "csv")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]


def test_cli_run_builtin_dry(tmp_path):
    r = _run("run-workflow", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "run-only",
             "--postprocess", "none",
             "--dry-run")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]
    assert p["dry_run"] is True
    assert p["executed"] is False


def test_cli_run_builtin_no_postprocess_ok(tmp_path):
    r = _run("run-workflow", "--builtin-model", "nai_3x3_verified",
             "--work-dir", str(tmp_path / "w"),
             "--workflow-mode", "run-only",
             "--postprocess", "none",
             "--dry-run")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert p["ok"]


# ==================================================================
# explicit reference_position works (no named reference point needed)
# ==================================================================

def test_explicit_reference_position_works_for_sweep(tmp_path):
    """With explicit --reference-position, sweep prepares correctly without named reference point."""
    from mcnp_research_skill.workflow.sweep import prepare_point_sweep
    from mcnp_research_skill.models.registry import resolve_deck_path

    deck = str(resolve_deck_path("nai_3x3_verified"))
    work = tmp_path / "w"
    result = prepare_point_sweep(
        input_path=deck,
        work_dir=str(work),
        distances=[10, 20],
        axis="z",
        reference_position=(0, 0, 0),
        direction=1,
        source_energy=0.662,
        nps="1e6",
        postprocess="none",
    )
    assert result["ok"] is True
    assert result["prepared_count"] == 2
    d10 = work / "d10" / "nai_3x3_verified.txt"
    assert d10.exists()
    text = d10.read_text(encoding="utf-8")
    assert "sdef pos=0 0 10 par=2 erg=0.662" in text
