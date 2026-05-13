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
