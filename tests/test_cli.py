import json
import math
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.cli import load_config


def write_config(path: Path, base_file: Path, output_dir: Path) -> Path:
    path.write_text(
        f"""base_file: "{base_file.as_posix()}"
output_dir: "{output_dir.as_posix()}"
distance_cm: 20
reference_point: "crystal_center"
nps: "10000000"
energies:
  - 0.662
composite_sources: []
custom_energy: null
geb_enabled: false
geb_params: null
mpi_command: "mpirun -np 17 mcnp5mpi.exe"
plot_output: "{(output_dir / 'spectra.png').as_posix()}"
""",
        encoding="utf-8",
    )
    return path


def write_minimal_spe(path: Path) -> Path:
    cal = {"a": -118.408, "b": 2.279, "c": -0.000349306}
    e_kev = 662.0
    delta = cal["b"] ** 2 - 4 * cal["c"] * (cal["a"] - e_kev)
    center = int((-cal["b"] + math.sqrt(delta)) / (2 * cal["c"])) if delta > 0 else 512
    channels = [0] * 2048
    for offset, count in [(-5, 40), (-3, 90), (0, 200), (3, 90), (5, 40)]:
        channels[max(0, min(len(channels) - 1, center + offset))] = count
    path.write_text(
        "$DATE_MEA:\n"
        "04/29/2026 12:00:00\n"
        "$DATA:\n"
        "0 2047\n"
        + "\n".join(str(value) for value in channels)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_load_config_parses_pipeline_yaml(tmp_path: Path) -> None:
    base_file = tmp_path / "b.txt"
    config_path = write_config(tmp_path / "pipeline.yaml", base_file, tmp_path / "work")

    config = load_config(str(config_path))

    assert config["base_file"] == base_file.as_posix()
    assert config["distance_cm"] == 20
    assert config["energies"] == [0.662]
    assert config["custom_energy"] is None
    assert config["geb_enabled"] is False


def test_top_level_cli_generate_inputs_dry_run_outputs_json(tmp_path: Path) -> None:
    base_file = tmp_path / "b.txt"
    base_file.write_text("e8 0 0.1\nf8:p,e 1\nnps 1\n", encoding="utf-8")
    config_path = write_config(tmp_path / "pipeline.yaml", base_file, tmp_path / "work")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "generate-inputs",
            "--config",
            str(config_path),
            "--dry-run",
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["planned_files"]
    assert completed.stderr == ""


def test_top_level_cli_defaults_to_dry_run(tmp_path: Path) -> None:
    base_file = tmp_path / "b.txt"
    base_file.write_text("e8 0 0.1\nf8:p,e 1\nnps 1\n", encoding="utf-8")
    output_dir = tmp_path / "work"
    config_path = write_config(tmp_path / "pipeline.yaml", base_file, output_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "generate-inputs",
            "--config",
            str(config_path),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["dry_run"] is True
    assert output_dir.exists() is False


def test_top_level_cli_outputs_ascii_safe_json_with_bom_input(tmp_path: Path) -> None:
    base_file = tmp_path / "b.txt"
    base_file.write_text("\ufeffe8 0 0.1\nf8:p,e 1\nnps 1\n", encoding="utf-8")
    config_path = write_config(tmp_path / "pipeline.yaml", base_file, tmp_path / "work")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "generate-inputs",
            "--config",
            str(config_path),
            "--dry-run",
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0
    completed.stdout.encode("ascii")
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True


def test_top_level_cli_returns_nonzero_for_failed_command(tmp_path: Path) -> None:
    missing_base = tmp_path / "missing.txt"
    config_path = write_config(tmp_path / "pipeline.yaml", missing_base, tmp_path / "work")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "generate-inputs",
            "--config",
            str(config_path),
            "--dry-run",
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["errors"]


def test_top_level_cli_fit_geb_from_spe_outputs_json(tmp_path: Path) -> None:
    spe_path = write_minimal_spe(tmp_path / "CS-137_4-29.spe")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "--json",
            "fit-geb-from-spe",
            "--spe",
            str(spe_path),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["energy_fwhm_pairs"]


def test_top_level_cli_origin_export_dry_run_outputs_json(tmp_path: Path) -> None:
    (tmp_path / "sample_Data.csv").write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "origin-export",
            "--target-dir",
            str(tmp_path),
            "--dry-run",
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["planned"]


def test_top_level_cli_origin_export_execute_without_confirm_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "sample_Data.csv").write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "origin-export",
            "--target-dir",
            str(tmp_path),
            "--execute",
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("confirm" in error.lower() for error in payload["errors"])


# ---------------------------------------------------------------------------
# generate-inputs with --profile-path / --profile-name
# ---------------------------------------------------------------------------


def _write_profiles_yaml(path: Path, *, active: str = "lab2", extra_profile: str | None = None) -> Path:
    lines = [
        f"active_profile: {active}",
        "profiles:",
        "  default:",
        "    detector:",
        "      reference_points:",
        "        crystal_center:",
        '          name: "几何中心"',
        "          z: 3.81",
        '          short_label: "Center"',
        "  lab2:",
        "    detector:",
        "      reference_points:",
        "        custom_center:",
        '          name: "Custom Center"',
        "          z: 12.34",
        '          short_label: "CC"',
    ]
    if extra_profile:
        lines.append(f"  {extra_profile}:")
        lines.append("    detector:")
        lines.append("      reference_points: {}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_minimal_config(path: Path, base_file: Path, output_dir: Path, reference_point: str = "crystal_center") -> Path:
    path.write_text(
        f'base_file: "{base_file.as_posix()}"\n'
        f'output_dir: "{output_dir.as_posix()}"\n'
        "distance_cm: 20\n"
        f'reference_point: "{reference_point}"\n'
        'nps: "10000000"\n'
        "energies:\n"
        "  - 0.662\n"
        "composite_sources: []\n"
        "custom_energy: null\n"
        "geb_enabled: false\n"
        'mpi_command: "echo"\n'
        f'plot_output: "{(output_dir / "spectra.png").as_posix()}"\n',
        encoding="utf-8",
    )
    return path


def test_generate_inputs_profile_custom_reference_point(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    config_path = _write_minimal_config(
        tmp_path / "cfg.yaml", base_file, tmp_path / "work", reference_point="custom_center"
    )

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "generate-inputs",
            "--config", str(config_path),
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    # z = 12.34 - 20.0 = -7.66
    content = payload["planned_files"][0]["content_preview"]
    assert "TR1 0 0 -7.6600" in content


def test_generate_inputs_profile_bad_reference_point_returns_json_error(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    config_path = _write_minimal_config(
        tmp_path / "cfg.yaml", base_file, tmp_path / "work", reference_point="nonexistent"
    )

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "generate-inputs",
            "--config", str(config_path),
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0, f"stdout={completed.stdout}"
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("nonexistent" in e for e in payload["errors"])


def test_generate_inputs_without_profile_uses_builtin_reference_points(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    config_path = _write_minimal_config(tmp_path / "cfg.yaml", base_file, tmp_path / "work")

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "generate-inputs",
            "--config", str(config_path),
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    content = payload["planned_files"][0]["content_preview"]
    # crystal_center z=3.81, distance=20 → -16.19
    assert "TR1 0 0 -16.1900" in content


# ---------------------------------------------------------------------------
# run-core-pipeline with --profile-path / --profile-name
# ---------------------------------------------------------------------------


def _write_pipeline_config(path: Path, base_file: Path, output_dir: Path, ref: str = "crystal_center") -> Path:
    plot = (output_dir / "spectra.png").as_posix()
    path.write_text(
        f'base_file: "{base_file.as_posix()}"\n'
        f'output_dir: "{output_dir.as_posix()}"\n'
        "distance_cm: 20\n"
        f'reference_point: "{ref}"\n'
        'nps: "10000000"\n'
        "energies:\n  - 0.662\n"
        "composite_sources: []\n"
        "custom_energy: null\n"
        "geb_enabled: false\n"
        'mpi_command: "echo"\n'
        f'plot_output: "{plot}"\n',
        encoding="utf-8",
    )
    return path


def test_pipeline_cli_with_profile_custom_reference_point(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "work"
    output_dir.mkdir()
    config_path = _write_pipeline_config(
        tmp_path / "cfg.yaml", base_file, output_dir, ref="custom_center"
    )

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "run-core-pipeline",
            "--config", str(config_path),
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, f"stderr={completed.stderr}"
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    gen = payload["steps"]["generate_inputs"]
    content = gen["planned_files"][0]["content_preview"]
    # custom_center z=12.34, distance=20 → -7.66
    assert "TR1 0 0 -7.6600" in content


def test_pipeline_cli_bad_profile_name_returns_json_error(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "work"
    output_dir.mkdir()
    config_path = _write_pipeline_config(tmp_path / "cfg.yaml", base_file, output_dir)

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "run-core-pipeline",
            "--config", str(config_path),
            "--profile-path", str(profiles_path),
            "--profile-name", "nonexistent",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("nonexistent" in e for e in payload["errors"])


# ---------------------------------------------------------------------------
# batch-run with --profile-path / --profile-name
# ---------------------------------------------------------------------------


def test_batch_cli_with_profile_custom_reference_point(tmp_path: Path):
    base_file = tmp_path / "A.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "run_test"

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "batch-run",
            "--base-file", str(base_file),
            "--output-dir", str(output_dir),
            "--reference-point", "custom_center",
            "--nps", "1000000",
            "--distance-start", "10",
            "--distance-end", "10",
            "--distance-step", "10",
            "--custom-energy-kev", "663.52",
            "--mpi-command", "echo",
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    subrun = payload["subruns"][0]
    gen = subrun["result"]["steps"]["generate_inputs"]
    content = gen["planned_files"][0]["content_preview"]
    # custom_center z=12.34, distance=10 → 2.34
    assert "TR1 0 0 2.3400" in content


def test_batch_cli_bad_profile_name_returns_json_error(tmp_path: Path):
    base_file = tmp_path / "A.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "run_test"

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "batch-run",
            "--base-file", str(base_file),
            "--output-dir", str(output_dir),
            "--reference-point", "crystal_center",
            "--nps", "1000000",
            "--distance-start", "10",
            "--distance-end", "10",
            "--distance-step", "10",
            "--custom-energy-kev", "663.52",
            "--mpi-command", "echo",
            "--profile-path", str(profiles_path),
            "--profile-name", "nonexistent",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("nonexistent" in e for e in payload["errors"])


def test_batch_cli_bad_reference_point_returns_json_error(tmp_path: Path):
    base_file = tmp_path / "A.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_profiles_yaml(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "run_test"

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "batch-run",
            "--base-file", str(base_file),
            "--output-dir", str(output_dir),
            "--reference-point", "ghost_point",
            "--nps", "1000000",
            "--distance-start", "10",
            "--distance-end", "10",
            "--distance-step", "10",
            "--custom-energy-kev", "663.52",
            "--mpi-command", "echo",
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("ghost_point" in e for e in payload["errors"])


# ---------------------------------------------------------------------------
# generate-inputs with profile nuclides
# ---------------------------------------------------------------------------


def _write_nuclides_profiles(path: Path) -> Path:
    path.write_text(
        "active_profile: lab2\n"
        "profiles:\n"
        "  lab2:\n"
        "    detector:\n"
        "      reference_points:\n"
        "        crystal_center:\n"
        '          name: "几何中心"\n'
        "          z: 3.81\n"
        '          short_label: "Center"\n'
        "    nuclides:\n"
        "      single_energy:\n"
        "        Test-100:\n"
        "        - 0.1\n"
        "      composite_sources: {}\n",
        encoding="utf-8",
    )
    return path


def test_generate_inputs_profile_custom_nuclide(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_nuclides_profiles(tmp_path / "profiles.yaml")
    config_path = _write_minimal_config(
        tmp_path / "cfg.yaml", base_file, tmp_path / "work",
        reference_point="crystal_center",
    )
    # Override config energies to use the custom nuclide
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "energies:\n  - 0.662", "energies:\n  - 0.1"
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "generate-inputs",
            "--config", str(config_path),
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    content = payload["planned_files"][0]["content_preview"]
    assert "Test-100" in content
    assert "erg=0.1" in content


def test_pipeline_cli_with_profile_nuclides(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_nuclides_profiles(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "work"
    output_dir.mkdir()
    (output_dir / "1.txt").write_text("e8 0 0.1\nf8:p,e 1\nnps 1\n", encoding="utf-8")
    (output_dir / "result.txt").write_text(
        "header\n     energy\n  0.100  1.0  0.01\n total  1.0  0.01\n",
        encoding="utf-8",
    )
    (output_dir / "existing_Data.csv").write_text(
        "Energy (MeV),Tally (Counts/Particle),Relative Error\n0.1,1.0,0.01\n",
        encoding="utf-8",
    )
    config_path = _write_pipeline_config(
        tmp_path / "cfg.yaml", base_file, output_dir, ref="crystal_center",
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "energies:\n  - 0.662", "energies:\n  - 0.1"
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "run-core-pipeline",
            "--config", str(config_path),
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    gen = payload["steps"]["generate_inputs"]
    content = gen["planned_files"][0]["content_preview"]
    assert "Test-100" in content


def test_batch_cli_with_profile_nuclides(tmp_path: Path):
    base_file = tmp_path / "A.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles_path = _write_nuclides_profiles(tmp_path / "profiles.yaml")
    output_dir = tmp_path / "run_test"

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "batch-run",
            "--base-file", str(base_file),
            "--output-dir", str(output_dir),
            "--reference-point", "crystal_center",
            "--nps", "1000000",
            "--distance-start", "10",
            "--distance-end", "10",
            "--distance-step", "10",
            "--custom-energy-kev", "100",  # 0.1 MeV → Test-100
            "--mpi-command", "echo",
            "--profile-path", str(profiles_path),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    subrun = payload["subruns"][0]
    gen = subrun["result"]["steps"]["generate_inputs"]
    content = gen["planned_files"][0]["content_preview"]
    # custom_energy 0.1 MeV → label should reflect 100 keV
    assert "100.00keV" in content


def test_generate_inputs_bad_nuclide_energy_returns_json_error(tmp_path: Path):
    base_file = tmp_path / "b.txt"
    base_file.write_text("f8:p,e 1\nnps 1\n", encoding="utf-8")
    profiles = tmp_path / "profiles.yaml"
    profiles.write_text(
        "active_profile: lab2\n"
        "profiles:\n"
        "  lab2:\n"
        "    detector:\n"
        "      reference_points:\n"
        "        crystal_center:\n"
        '          name: "几何中心"\n'
        "          z: 3.81\n"
        "    nuclides:\n"
        "      single_energy:\n"
        "        Bad:\n"
        "        - not_a_number\n",
        encoding="utf-8",
    )
    config_path = _write_minimal_config(
        tmp_path / "cfg.yaml", base_file, tmp_path / "work",
    )

    completed = subprocess.run(
        [
            sys.executable, "-m", "mcnp_research_skill.cli", "generate-inputs",
            "--config", str(config_path),
            "--profile-path", str(profiles),
            "--profile-name", "lab2",
            "--dry-run",
        ],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert any("Bad" in e for e in payload["errors"])


# ---------------------------------------------------------------------------
# run-mpi --input-files
# ---------------------------------------------------------------------------


def test_run_mpi_cli_input_files(tmp_path: Path):
    (tmp_path / "A.txt").write_text(
        "f8:p,e 1\nnps 100\nc Meta_ID:Cs-137 (662 keV) | Dist:20cm | Ref:几何中心\n",
        encoding="utf-8",
    )
    (tmp_path / "1.txt").write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")
    config = tmp_path / "cfg.yaml"
    config.write_text(
        f'output_dir: "{tmp_path.as_posix()}"\n'
        'mpi_command: "echo"\n',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "-m", "mcnp_research_skill.cli", "run-mpi",
         "--config", str(config), "--input-files", "A.txt", "--dry-run"],
        cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    names = [p["input_file"] for p in payload["planned"]]
    assert "A.txt" in names
    assert "1.txt" not in names
