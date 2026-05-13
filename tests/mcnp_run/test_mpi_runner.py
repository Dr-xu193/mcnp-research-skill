from pathlib import Path

from mcnp_research_skill.mcnp_run.mpi_runner import run_mpi_batch


def write_input(path: Path, meta: str = "Cs-137 (662 keV)", dist: str = "20.0cm", ref: str = "几何中心") -> Path:
    path.write_text(
        f"c Meta_ID:{meta} | Dist:{dist} | Ref:{ref}\n"
        "f8:p,e 1\n"
        "nps 1000\n",
        encoding="utf-8",
    )
    return path


def test_run_mpi_batch_selects_only_numeric_txt_files(tmp_path: Path) -> None:
    write_input(tmp_path / "1.txt")
    write_input(tmp_path / "abc.txt")
    (tmp_path / "2.csv").write_text("ignored", encoding="utf-8")

    result = run_mpi_batch(str(tmp_path), "mpirun -np 2 mcnp5mpi.exe")

    assert result["ok"] is True
    assert [item["input_file"] for item in result["planned"]] == ["1.txt"]


def test_run_mpi_batch_sorts_numeric_txt_files_by_number(tmp_path: Path) -> None:
    write_input(tmp_path / "10.txt")
    write_input(tmp_path / "2.txt")
    write_input(tmp_path / "1.txt")

    result = run_mpi_batch(str(tmp_path), "mpirun")

    assert [item["input_file"] for item in result["planned"]] == ["1.txt", "2.txt", "10.txt"]


def test_run_mpi_batch_builds_output_name_from_meta_dist_ref(tmp_path: Path) -> None:
    write_input(tmp_path / "1.txt", meta="Cs-137 (662 keV)", dist="20.0cm", ref="几何中心")

    result = run_mpi_batch(str(tmp_path), "mpirun")

    assert result["planned"][0]["output_file"] == "Cs-137_662keV-20.0cm-几何中心.txt"
    assert result["planned"][0]["command"] == "mpirun i=i.txt o=o.txt"


def test_run_mpi_batch_appends_counter_when_output_name_exists(tmp_path: Path) -> None:
    write_input(tmp_path / "1.txt", meta="Cs-137 (662 keV)", dist="20.0cm", ref="几何中心")
    (tmp_path / "Cs-137_662keV-20.0cm-几何中心.txt").write_text("existing", encoding="utf-8")

    result = run_mpi_batch(str(tmp_path), "mpirun")

    assert result["planned"][0]["output_file"] == "Cs-137_662keV-20.0cm-几何中心_1.txt"


def test_run_mpi_batch_dry_run_does_not_copy_run_delete_or_cleanup(tmp_path: Path, monkeypatch) -> None:
    write_input(tmp_path / "1.txt")
    (tmp_path / "o.txt").write_text("old output", encoding="utf-8")
    (tmp_path / "runt123").write_text("temp", encoding="utf-8")

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("subprocess.run must not be called during dry_run")

    monkeypatch.setattr("mcnp_research_skill.mcnp_run.mpi_runner.subprocess.run", fail_run)

    result = run_mpi_batch(str(tmp_path), "mpirun", dry_run=True)

    assert result["ok"] is True
    assert not (tmp_path / "i.txt").exists()
    assert (tmp_path / "o.txt").read_text(encoding="utf-8") == "old output"
    assert (tmp_path / "runt123").exists()
    assert result["completed"] == []
    assert result["cleanup"] == []


def test_run_mpi_batch_rejects_real_run_without_confirmation(tmp_path: Path) -> None:
    write_input(tmp_path / "1.txt")

    result = run_mpi_batch(str(tmp_path), "mpirun", dry_run=False, confirm=False)

    assert result["ok"] is False
    assert result["planned"] == []
    assert any("confirm" in error.lower() for error in result["errors"])


def test_run_mpi_batch_returns_error_when_target_dir_missing(tmp_path: Path) -> None:
    result = run_mpi_batch(str(tmp_path / "missing"), "mpirun")

    assert result["ok"] is False
    assert result["errors"]


def test_run_mpi_batch_warns_when_no_numeric_txt_files(tmp_path: Path) -> None:
    write_input(tmp_path / "abc.txt")

    result = run_mpi_batch(str(tmp_path), "mpirun")

    assert result["ok"] is False
    assert result["planned"] == []
    assert result["warnings"]


def test_run_mpi_batch_dry_run_can_plan_from_generated_inputs_without_files(tmp_path: Path, monkeypatch) -> None:
    target_dir = tmp_path / "missing-work"
    planned_input_files = [
        {
            "file_name": "1.txt",
            "path": str(target_dir / "1.txt"),
            "meta_id": "Cs-137 (662 keV)",
            "distance_cm": 20.0,
            "reference_short": "几何中心",
        }
    ]

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("subprocess.run must not be called during planned dry_run")

    def fail_copy(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("shutil.copyfile must not be called during planned dry_run")

    monkeypatch.setattr("mcnp_research_skill.mcnp_run.mpi_runner.subprocess.run", fail_run)
    monkeypatch.setattr("mcnp_research_skill.mcnp_run.mpi_runner.shutil.copyfile", fail_copy)

    result = run_mpi_batch(
        str(target_dir),
        "mpirun -np 1 mcnp5mpi.exe",
        dry_run=True,
        planned_input_files=planned_input_files,
    )

    assert result["ok"] is True
    assert result["used_planned_inputs"] is True
    assert result["planned"][0]["input_file"] == "1.txt"
    assert result["planned"][0]["output_file"] == "Cs-137_662keV-20.0cm-几何中心.txt"
    assert result["commands"] == ["mpirun -np 1 mcnp5mpi.exe i=i.txt o=o.txt"]
    assert not target_dir.exists()


def test_run_mpi_batch_real_run_ignores_planned_inputs_and_requires_real_files(tmp_path: Path) -> None:
    result = run_mpi_batch(
        str(tmp_path),
        "mpirun",
        dry_run=False,
        confirm=True,
        planned_input_files=[
            {
                "file_name": "1.txt",
                "path": str(tmp_path / "1.txt"),
                "meta_id": "Cs-137",
                "distance_cm": 20,
                "reference_short": "几何中心",
            }
        ],
    )

    assert result["ok"] is False
    assert result["used_planned_inputs"] is False
    assert result["planned"] == []
    assert result["warnings"]


def test_run_mpi_batch_real_run_uses_fake_subprocess_and_cleans_temp_files(tmp_path: Path, monkeypatch) -> None:
    write_input(tmp_path / "1.txt", meta="Cs-137", dist="20cm", ref="晶体表面")
    (tmp_path / "runt123").write_text("temp", encoding="utf-8")

    calls = []

    def fake_run(command, shell, cwd, stdout, stderr):  # noqa: ANN001
        calls.append({"command": command, "shell": shell, "cwd": cwd})
        (Path(cwd) / "o.txt").write_text("mcnp output", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = b""
            stderr = b""

        return Completed()

    monkeypatch.setattr("mcnp_research_skill.mcnp_run.mpi_runner.subprocess.run", fake_run)

    result = run_mpi_batch(str(tmp_path), "mpirun", dry_run=False, confirm=True)

    assert result["ok"] is True
    assert calls == [{"command": "mpirun i=i.txt o=o.txt", "shell": True, "cwd": str(tmp_path)}]
    assert (tmp_path / "Cs-137-20cm-晶体表面.txt").read_text(encoding="utf-8") == "mcnp output"
    assert not (tmp_path / "i.txt").exists()
    assert not (tmp_path / "o.txt").exists()
    assert not (tmp_path / "runt123").exists()
    assert result["completed"][0]["output_file"] == "Cs-137-20cm-晶体表面.txt"
