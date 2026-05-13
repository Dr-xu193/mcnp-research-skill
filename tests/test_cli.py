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
