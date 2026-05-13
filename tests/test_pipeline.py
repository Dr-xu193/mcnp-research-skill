from pathlib import Path

from mcnp_research_skill.pipeline import run_core_pipeline


def write_base(path: Path) -> Path:
    path.write_text("e8 0 0.1\nf8:p,e 1\nnps 1\n", encoding="utf-8")
    return path


def write_output_txt(path: Path) -> Path:
    path.write_text(
        "header\n"
        "     energy\n"
        "  0.100  1.0  0.01\n"
        " total  1.0  0.01\n",
        encoding="utf-8",
    )
    return path


def base_config(tmp_path: Path) -> dict:
    base_file = write_base(tmp_path / "b.txt")
    output_dir = tmp_path / "work"
    return {
        "base_file": str(base_file),
        "output_dir": str(output_dir),
        "distance_cm": 20,
        "reference_point": "crystal_center",
        "nps": "10000000",
        "energies": [0.662],
        "composite_sources": [],
        "custom_energy": None,
        "geb_enabled": False,
        "geb_params": None,
        "mpi_command": "mpirun -np 17 mcnp5mpi.exe",
        "plot_output": str(output_dir / "spectra.png"),
    }


def test_pipeline_dry_run_does_not_write_files_or_run_mpi(tmp_path: Path, monkeypatch) -> None:
    config = base_config(tmp_path)
    output_dir = Path(config["output_dir"])
    output_dir.mkdir()
    write_base(output_dir / "1.txt")
    write_output_txt(output_dir / "result.txt")
    csv_path = output_dir / "existing_Data.csv"
    csv_path.write_text(
        "Energy (MeV),Tally (Counts/Particle),Relative Error\n0.1,1.0,0.01\n",
        encoding="utf-8",
    )
    old_o = output_dir / "o.txt"
    old_o.write_text("old", encoding="utf-8")

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("MPI subprocess must not run during pipeline dry_run")

    monkeypatch.setattr("mcnp_research_skill.mcnp_run.mpi_runner.subprocess.run", fail_run)

    result = run_core_pipeline(config, dry_run=True)

    assert result["dry_run"] is True
    assert result["steps"]["generate_inputs"]["planned_files"]
    assert not (output_dir / "2.txt").exists()
    assert old_o.read_text(encoding="utf-8") == "old"
    assert not Path(config["plot_output"]).exists()


def test_pipeline_dry_run_plans_across_steps_without_real_input_files(tmp_path: Path, monkeypatch) -> None:
    config = base_config(tmp_path)
    output_dir = Path(config["output_dir"])

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("MPI subprocess must not run during pipeline dry_run")

    monkeypatch.setattr("mcnp_research_skill.mcnp_run.mpi_runner.subprocess.run", fail_run)

    result = run_core_pipeline(config, dry_run=True)

    assert result["ok"] is True
    assert result["steps"]["generate_inputs"]["ok"] is True
    assert result["steps"]["run_mpi"]["ok"] is True
    assert result["steps"]["run_mpi"]["used_planned_inputs"] is True
    assert result["steps"]["extract_csv"]["ok"] is True
    assert result["steps"]["extract_csv"]["planned_from_mpi"] is True
    assert result["steps"]["plot_spectra"]["ok"] is True
    assert result["steps"]["plot_spectra"]["planned_from_pipeline"] is True
    assert result["steps"]["plot_spectra"]["csv_files"] == [
        str(output_dir / "Cs-137_662keV-20.0cm-几何中心_Data.csv")
    ]
    assert not (output_dir / "1.txt").exists()
    assert not (output_dir / "i.txt").exists()
    assert not (output_dir / "o.txt").exists()
    assert not Path(config["plot_output"]).exists()


def test_run_core_pipeline_calls_four_steps_in_order(tmp_path: Path, monkeypatch) -> None:
    config = base_config(tmp_path)
    output_dir = Path(config["output_dir"])
    output_dir.mkdir()
    csv_path = output_dir / "result_Data.csv"
    csv_path.write_text(
        "Energy (MeV),Tally (Counts/Particle),Relative Error\n0.1,1.0,0.01\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_generate_mcnp_inputs(**kwargs):  # noqa: ANN003
        calls.append("generate_inputs")
        return {"ok": True, "warnings": [], "errors": [], "generated_files": [{"path": str(output_dir / "1.txt")}], "planned_files": []}

    def fake_run_mpi_batch(**kwargs):  # noqa: ANN003
        calls.append("run_mpi")
        return {"ok": True, "warnings": [], "errors": [], "completed": [{"output_path": str(output_dir / "result.txt")}], "planned": []}

    def fake_extract_tally_csvs(**kwargs):  # noqa: ANN003
        calls.append("extract_csv")
        return {"ok": True, "warnings": [], "errors": [], "csv_files": [str(csv_path)], "planned_files": [], "count": 1}

    def fake_plot_spectra(**kwargs):  # noqa: ANN003
        calls.append("plot_spectra")
        return {"ok": True, "warnings": [], "errors": [], "dry_run": kwargs["dry_run"], "csv_files": kwargs["csv_files"]}

    monkeypatch.setattr("mcnp_research_skill.pipeline.generate_mcnp_inputs", fake_generate_mcnp_inputs)
    monkeypatch.setattr("mcnp_research_skill.pipeline.run_mpi_batch", fake_run_mpi_batch)
    monkeypatch.setattr("mcnp_research_skill.pipeline.extract_tally_csvs", fake_extract_tally_csvs)
    monkeypatch.setattr("mcnp_research_skill.pipeline.plot_spectra", fake_plot_spectra)

    result = run_core_pipeline(config, dry_run=False, confirm_mpi=True)

    assert result["ok"] is True
    assert calls == ["generate_inputs", "run_mpi", "extract_csv", "plot_spectra"]


def test_run_core_pipeline_skips_later_steps_when_generate_inputs_fails(tmp_path: Path, monkeypatch) -> None:
    config = base_config(tmp_path)

    def fake_generate_mcnp_inputs(**kwargs):  # noqa: ANN003
        return {"ok": False, "warnings": [], "errors": ["bad base file"]}

    def forbidden_step(**kwargs):  # noqa: ANN003
        raise AssertionError("later steps must be skipped after generate_inputs fails")

    monkeypatch.setattr("mcnp_research_skill.pipeline.generate_mcnp_inputs", fake_generate_mcnp_inputs)
    monkeypatch.setattr("mcnp_research_skill.pipeline.run_mpi_batch", forbidden_step)
    monkeypatch.setattr("mcnp_research_skill.pipeline.extract_tally_csvs", forbidden_step)
    monkeypatch.setattr("mcnp_research_skill.pipeline.plot_spectra", forbidden_step)

    result = run_core_pipeline(config, dry_run=True)

    assert result["ok"] is False
    assert result["steps"]["run_mpi"]["skipped"] is True
    assert result["steps"]["extract_csv"]["skipped"] is True
    assert result["steps"]["plot_spectra"]["skipped"] is True
    assert "bad base file" in result["errors"]


def test_run_core_pipeline_skips_plot_when_no_csv_files_exist(tmp_path: Path, monkeypatch) -> None:
    config = base_config(tmp_path)
    Path(config["output_dir"]).mkdir()

    def fake_generate_mcnp_inputs(**kwargs):  # noqa: ANN003
        return {"ok": True, "warnings": [], "errors": []}

    def fake_run_mpi_batch(**kwargs):  # noqa: ANN003
        return {"ok": True, "warnings": [], "errors": []}

    def fake_extract_tally_csvs(**kwargs):  # noqa: ANN003
        return {"ok": True, "warnings": [], "errors": [], "csv_files": [], "planned_files": [], "count": 0}

    def forbidden_plot(**kwargs):  # noqa: ANN003
        raise AssertionError("plot_spectra must be skipped when no CSV files exist")

    monkeypatch.setattr("mcnp_research_skill.pipeline.generate_mcnp_inputs", fake_generate_mcnp_inputs)
    monkeypatch.setattr("mcnp_research_skill.pipeline.run_mpi_batch", fake_run_mpi_batch)
    monkeypatch.setattr("mcnp_research_skill.pipeline.extract_tally_csvs", fake_extract_tally_csvs)
    monkeypatch.setattr("mcnp_research_skill.pipeline.plot_spectra", forbidden_plot)

    result = run_core_pipeline(config, dry_run=True)

    assert result["ok"] is True
    assert result["steps"]["plot_spectra"]["skipped"] is True
    assert any("csv" in warning.lower() for warning in result["warnings"])
