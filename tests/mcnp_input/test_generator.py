from pathlib import Path

from mcnp_research_skill.mcnp_input.generator import generate_mcnp_inputs


def write_base(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def base_model(*, nps: bool = True, geb: bool = False, tally: bool = True) -> str:
    lines = [
        "c base model",
        "sdef old source",
        "si1 old",
        "sp1 old",
        "tr1 1 2 3",
        "e8 0 0.1 0.2",
    ]
    if geb:
        lines.append("FT8 GEB 1 2 3")
    if tally:
        lines.append("f8:p,e 1")
    if nps:
        lines.append("nps 1")
    return "\n".join(lines) + "\n"


def only_content(result: dict) -> str:
    planned = result["planned_files"] or result["generated_files"]
    return planned[0]["content_preview"]


def test_generate_mcnp_inputs_dry_run_does_not_write_files(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())
    output_dir = tmp_path / "out"

    result = generate_mcnp_inputs(
        base_file=str(base_file),
        output_dir=str(output_dir),
        distance_cm=20.0,
        reference_point="crystal_center",
        nps="10000000",
        energies=[0.662],
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert output_dir.exists() is False
    assert result["planned_files"][0]["file_name"] == "1.txt"
    assert result["generated_files"] == []


def test_generate_mcnp_inputs_replaces_existing_nps(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model(nps=True))

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000 (10^7)",
        energies=[0.662],
        dry_run=True,
    )

    content = only_content(result)
    assert "nps 10000000" in content
    assert "\nnps 1\n" not in content


def test_generate_mcnp_inputs_appends_nps_when_missing(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model(nps=False))

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "12345",
        energies=[0.662],
        dry_run=True,
    )

    assert "nps 12345" in only_content(result)


def test_generate_mcnp_inputs_computes_tr1_z_from_reference_and_distance(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        dry_run=True,
    )

    assert result["metadata"]["z_cm"] == "-16.1900"
    assert "TR1 0 0 -16.1900" in only_content(result)


def test_generate_mcnp_inputs_generates_cs137_single_energy(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        dry_run=True,
    )

    planned = result["planned_files"][0]
    assert planned["meta_id"] == "Cs-137 (662 keV)"
    assert "erg=0.662" in planned["content_preview"]
    assert "c Meta_ID:Cs-137 (662 keV) | Dist:20.0cm | Ref:几何中心" in planned["content_preview"]


def test_generate_mcnp_inputs_generates_co60_composite_si2_sp2(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000",
        energies=[],
        composite_sources=["co60"],
        dry_run=True,
    )

    content = only_content(result)
    assert result["planned_files"][0]["meta_id"] == "Co-60_Composite"
    assert "erg=d2" in content
    assert "si2 L 1.1732 1.3325" in content
    assert "sp2 0.9985 0.9998" in content


def test_generate_mcnp_inputs_injects_geb_when_enabled(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        geb_enabled=True,
        geb_params={"a": "-0.00789", "b": "0.06769", "c": "0.21159"},
        dry_run=True,
    )

    content = only_content(result)
    assert "e8 0 0.1 0.2\nFT8 GEB -0.00789 0.06769 0.21159" in content


def test_generate_mcnp_inputs_removes_existing_geb_when_disabled(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model(geb=True))

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        geb_enabled=False,
        dry_run=True,
    )

    assert "FT8 GEB" not in only_content(result)


def test_generate_mcnp_inputs_reports_warning_when_f8_card_missing(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model(tally=False))

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        dry_run=True,
    )

    assert result["ok"] is False
    assert result["planned_files"] == []
    assert any("f8:p,e" in warning.lower() for warning in result["warnings"])


def test_generate_mcnp_inputs_writes_incrementing_numeric_files(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "3.txt").write_text("existing", encoding="utf-8")

    result = generate_mcnp_inputs(
        str(base_file),
        str(output_dir),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        dry_run=False,
    )

    generated = result["generated_files"][0]
    written_path = Path(generated["path"])
    assert generated["file_name"] == "4.txt"
    assert written_path.exists()
    assert "Meta_ID:Cs-137 (662 keV)" in written_path.read_text(encoding="utf-8")


def test_generate_mcnp_inputs_creates_missing_output_dir_when_writing(tmp_path: Path) -> None:
    base_file = write_base(tmp_path / "b.txt", base_model())
    output_dir = tmp_path / "missing-out"

    result = generate_mcnp_inputs(
        str(base_file),
        str(output_dir),
        20.0,
        "crystal_center",
        "10000000",
        energies=[0.662],
        dry_run=False,
    )

    assert result["ok"] is True
    assert output_dir.exists()
    assert (output_dir / "1.txt").exists()


# ---------------------------------------------------------------------------
# resolve_reference_point
# ---------------------------------------------------------------------------


def test_resolve_reference_point_builtin_default():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    rp = resolve_reference_point("crystal_center")
    assert rp["z"] == 3.81
    assert rp["short"] == "几何中心"


def test_resolve_reference_point_unknown_raises_valueerror():
    import pytest
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    with pytest.raises(ValueError, match="missing_point"):
        resolve_reference_point("missing_point")
    with pytest.raises(ValueError, match="crystal_center"):
        resolve_reference_point("missing_point")


def test_resolve_reference_point_profile_key_match():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    custom_rps = {
        "custom_center": {"name": "Custom Center", "z": 12.34, "short_label": "CC"},
    }
    rp = resolve_reference_point("custom_center", custom_rps)
    assert rp["z"] == 12.34
    assert rp["short"] == "Custom Center"


def test_resolve_reference_point_profile_name_match():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    custom_rps = {
        "custom_center": {"name": "Custom Center", "z": 12.34, "short_label": "CC"},
    }
    rp = resolve_reference_point("Custom Center", custom_rps)
    assert rp["z"] == 12.34


def test_resolve_reference_point_profile_short_label_match():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    custom_rps = {
        "custom_center": {"name": "Custom Center", "z": 12.34, "short_label": "CC"},
    }
    rp = resolve_reference_point("CC", custom_rps)
    assert rp["z"] == 12.34


def test_resolve_reference_point_falls_back_to_builtin():
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    custom_rps = {"custom_center": {"name": "Custom Center", "z": 12.34}}
    # "crystal_center" is not in custom_rps, but is in built-in
    rp = resolve_reference_point("crystal_center", custom_rps)
    assert rp["z"] == 3.81


def test_resolve_reference_point_missing_z_raises_valueerror():
    import pytest
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    bad_rps = {"bad": {"name": "Bad Point"}}
    with pytest.raises(ValueError, match="bad"):
        resolve_reference_point("bad", bad_rps)


def test_resolve_reference_point_non_numeric_z_raises_valueerror():
    import pytest
    from mcnp_research_skill.mcnp_input.generator import resolve_reference_point

    bad_rps = {"bad": {"name": "Bad", "z": "not_a_number"}}
    with pytest.raises(ValueError, match="bad"):
        resolve_reference_point("bad", bad_rps)


# ---------------------------------------------------------------------------
# generate_mcnp_inputs with profile reference_points
# ---------------------------------------------------------------------------


def test_generator_uses_profile_z_for_tr1(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())

    custom_rps = {
        "custom_center": {"name": "Custom Center", "z": 12.34, "short_label": "CC"},
    }
    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "custom_center",
        "10000000",
        energies=[0.662],
        dry_run=True,
        reference_points=custom_rps,
    )

    assert result["ok"] is True
    # z = 12.34 - 20.0 = -7.66 → "-7.6600"
    assert result["metadata"]["z_cm"] == "-7.6600"
    content = result["planned_files"][0]["content_preview"]
    assert "TR1 0 0 -7.6600" in content


def test_generator_reports_error_for_bad_reference_point(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())

    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        20.0,
        "nonexistent_center",
        "10000000",
        energies=[0.662],
        dry_run=True,
    )

    assert result["ok"] is False
    assert any("nonexistent_center" in e for e in result["errors"])
    assert any("crystal_center" in e for e in result["errors"])


def test_generator_uses_profile_name_match_for_metadata(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())

    custom_rps = {
        "lab_ref": {"name": "Lab Reference Point", "z": 5.0, "short_label": "LR"},
    }
    result = generate_mcnp_inputs(
        str(base_file),
        str(tmp_path / "out"),
        10.0,
        "Lab Reference Point",
        "10000000",
        energies=[0.662],
        dry_run=True,
        reference_points=custom_rps,
    )

    assert result["ok"] is True
    assert result["metadata"]["reference_short"] == "Lab Reference Point"
    # z = 5.0 - 10.0 = -5.0
    assert "TR1 0 0 -5.0000" in result["planned_files"][0]["content_preview"]


# ---------------------------------------------------------------------------
# nuclides profile support
# ---------------------------------------------------------------------------


def test_generator_uses_profile_single_energy(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {"single_energy": {"Test-100": [0.1]}}
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[0.1], dry_run=True, nuclides=nuclides,
    )
    assert result["ok"] is True
    planned = result["planned_files"][0]
    assert planned["meta_id"] == "Test-100 (100 keV)"
    assert "erg=0.1" in planned["content_preview"]


def test_generator_profile_energy_overrides_builtin(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {"single_energy": {"Cs-137": [0.700]}}
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[0.700], dry_run=True, nuclides=nuclides,
    )
    assert result["ok"] is True
    planned = result["planned_files"][0]
    assert planned["meta_id"] == "Cs-137 (700 keV)"
    assert "erg=0.7" in planned["content_preview"]


def test_generator_profile_composite_source(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {
        "composite_sources": {
            "test_cs": {
                "meta_id": "Test_Composite",
                "cards": "si2 L 0.1 0.2\nsp2 1.0 1.0\n",
                "aliases": ["test"],
            },
        },
    }
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[], composite_sources=["test"], dry_run=True,
        nuclides=nuclides,
    )
    assert result["ok"] is True
    planned = result["planned_files"][0]
    assert planned["meta_id"] == "Test_Composite"
    content = planned["content_preview"]
    assert "si2 L 0.1 0.2" in content
    assert "sp2 1.0 1.0" in content


def test_generator_nuclides_bad_energy_raises(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {"single_energy": {"Bad": ["not_a_number"]}}
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[], dry_run=True, nuclides=nuclides,
    )
    assert result["ok"] is False
    assert any("Bad" in e for e in result["errors"])


def test_generator_nuclides_bad_composite_raises(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {"composite_sources": {"bad": {"meta_id": "X"}}}  # missing cards
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[], dry_run=True, nuclides=nuclides,
    )
    assert result["ok"] is False
    assert any("cards" in e.lower() for e in result["errors"])


def test_generator_without_nuclides_uses_defaults(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[0.662], dry_run=True,
    )
    assert result["ok"] is True
    assert result["planned_files"][0]["meta_id"] == "Cs-137 (662 keV)"


def test_nuclides_constants_not_mutated():
    from mcnp_research_skill.mcnp_input.constants import (
        COMPOSITE_ALIASES,
        COMPOSITE_SOURCES,
        ENERGY_DICT,
    )
    from mcnp_research_skill.mcnp_input.generator import (
        _normalize_profile_composite_sources,
        _normalize_profile_single_energy,
    )
    ed_before = dict(ENERGY_DICT)
    cs_before = dict(COMPOSITE_SOURCES)
    ca_before = dict(COMPOSITE_ALIASES)

    _normalize_profile_single_energy({"Test": [0.1]})
    _normalize_profile_composite_sources({"test": {"meta_id": "T", "cards": "si2 L\n"}})

    assert ENERGY_DICT == ed_before
    assert COMPOSITE_SOURCES == cs_before
    assert COMPOSITE_ALIASES == ca_before


def test_composite_source_cards_must_be_string(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {
        "composite_sources": {
            "bad": {"meta_id": "X", "cards": ["line1", "line2"]},
        },
    }
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[], dry_run=True, nuclides=nuclides,
    )
    assert result["ok"] is False
    assert any("cards" in e.lower() and "string" in e.lower() for e in result["errors"])


def test_composite_source_aliases_must_be_list(tmp_path: Path):
    base_file = write_base(tmp_path / "b.txt", base_model())
    nuclides = {
        "composite_sources": {
            "bad": {"meta_id": "X", "cards": "si2 L\n", "aliases": "not_a_list"},
        },
    }
    result = generate_mcnp_inputs(
        str(base_file), str(tmp_path / "out"), 20.0, "crystal_center",
        "10000000", energies=[], dry_run=True, nuclides=nuclides,
    )
    assert result["ok"] is False
    assert any("aliases" in e.lower() and "list" in e.lower() for e in result["errors"])
