from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.batch import expand_distance_range, kev_to_mev, run_batch_pipeline


def _write_base(path: Path) -> Path:
    path.write_text("e8 0 0.1\nf8:p,e 1\nnps 100\n", encoding="utf-8")
    return path


def _batch_config(base_file: Path, output_dir: Path) -> dict[str, object]:
    return {
        "base_file": str(base_file),
        "output_dir": str(output_dir),
        "reference_point": "crystal_center",
        "nps": "1000000",
        "distance_start": 16.3,
        "distance_end": 36.3,
        "distance_step": 5,
        "custom_energy_kev": 663.52,
        "geb_enabled": True,
        "geb_params": {"a": 0.2, "b": 0.3, "c": 0.6},
        "mpi_command": sys.executable,
    }


def test_expand_distance_range_includes_endpoint() -> None:
    assert expand_distance_range(16.3, 36.3, 5) == [16.3, 21.3, 26.3, 31.3, 36.3]


def test_kev_to_mev_conversion() -> None:
    assert kev_to_mev(663.52) == 0.66352


def test_batch_dry_run_plans_all_distances_without_writing_files(tmp_path: Path) -> None:
    base_file = _write_base(tmp_path / "A.txt")
    output_dir = tmp_path / "run_663"

    result = run_batch_pipeline(_batch_config(base_file, output_dir), dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["distances_cm"] == [16.3, 21.3, 26.3, 31.3, 36.3]
    assert len(result["subruns"]) == 5
    assert result["manifest_preview"]["base_file_sha256"]
    assert not output_dir.exists()
    assert not (output_dir / "manifest.json").exists()
    assert not list(tmp_path.glob("**/*.png"))
    assert not list(tmp_path.glob("**/*_Data.csv"))


def test_batch_execute_requires_confirm_before_any_write(tmp_path: Path) -> None:
    base_file = _write_base(tmp_path / "A.txt")
    output_dir = tmp_path / "run_663"

    result = run_batch_pipeline(_batch_config(base_file, output_dir), dry_run=False, confirm_mpi=False)

    assert result["ok"] is False
    assert any("confirm_mpi" in error for error in result["errors"])
    assert not output_dir.exists()


def test_batch_execute_writes_manifest_with_fake_core_pipeline(tmp_path: Path, monkeypatch) -> None:
    base_file = _write_base(tmp_path / "A.txt")
    output_dir = tmp_path / "run_663"
    seen_configs: list[dict[str, object]] = []

    def fake_run_core_pipeline(config: dict, dry_run: bool, confirm_mpi: bool, reference_points=None, nuclides=None):  # noqa: ANN001
        seen_configs.append(config)
        assert dry_run is False
        assert confirm_mpi is True
        assert reference_points is None
        return {
            "ok": True,
            "dry_run": False,
            "steps": {
                "generate_inputs": {"ok": True, "generated_files": []},
                "run_mpi": {"ok": True, "completed": []},
                "extract_csv": {"ok": True, "csv_files": []},
                "plot_spectra": {"ok": True, "written_files": []},
            },
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr("mcnp_research_skill.batch.run_core_pipeline", fake_run_core_pipeline)

    result = run_batch_pipeline(_batch_config(base_file, output_dir), dry_run=False, confirm_mpi=True)

    assert result["ok"] is True
    assert len(seen_configs) == 5
    assert seen_configs[0]["distance_cm"] == 16.3
    assert seen_configs[0]["custom_energy"] == 0.66352
    assert str(seen_configs[0]["output_dir"]).endswith("distance_16.3cm")
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["dry_run"] is False
    assert manifest["subruns"][0]["distance_cm"] == 16.3


def test_cli_batch_run_dry_run_outputs_json(tmp_path: Path) -> None:
    base_file = _write_base(tmp_path / "A.txt")
    output_dir = tmp_path / "run_663"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "batch-run",
            "--base-file",
            str(base_file),
            "--output-dir",
            str(output_dir),
            "--reference-point",
            "crystal_center",
            "--nps",
            "1000000",
            "--distance-start",
            "16.3",
            "--distance-end",
            "36.3",
            "--distance-step",
            "5",
            "--custom-energy-kev",
            "663.52",
            "--geb",
            "0.2",
            "0.3",
            "0.6",
            "--mpi-command",
            sys.executable,
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
    assert payload["distances_cm"] == [16.3, 21.3, 26.3, 31.3, 36.3]
    assert output_dir.exists() is False
    assert completed.stderr == ""


# ---------------------------------------------------------------------------
# run_batch_pipeline with reference_points
# ---------------------------------------------------------------------------


def test_batch_passes_reference_points_to_subruns(tmp_path: Path, monkeypatch) -> None:
    base_file = _write_base(tmp_path / "A.txt")
    output_dir = tmp_path / "run_test"
    custom_rps = {
        "custom_center": {"name": "Custom Center", "z": 5.0, "short_label": "CC"},
    }
    seen_rps: list[dict | None] = []

    def fake_run_core_pipeline(
        config: dict, dry_run: bool, confirm_mpi: bool, reference_points=None, nuclides=None
    ):  # noqa: ANN001
        seen_rps.append(reference_points)
        return {
            "ok": True,
            "dry_run": dry_run,
            "steps": {
                "generate_inputs": {"ok": True, "generated_files": []},
                "run_mpi": {"ok": True, "completed": []},
                "extract_csv": {"ok": True, "csv_files": []},
                "plot_spectra": {"ok": True, "written_files": []},
            },
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr("mcnp_research_skill.batch.run_core_pipeline", fake_run_core_pipeline)

    result = run_batch_pipeline(
        _batch_config(base_file, output_dir), dry_run=True, reference_points=custom_rps
    )

    assert result["ok"] is True
    assert len(seen_rps) == 5
    for rp in seen_rps:
        assert rp == custom_rps


def test_batch_without_reference_points_passes_none(tmp_path: Path, monkeypatch) -> None:
    base_file = _write_base(tmp_path / "A.txt")
    output_dir = tmp_path / "run_test"
    seen_rps: list[dict | None] = []

    def fake_run_core_pipeline(
        config: dict, dry_run: bool, confirm_mpi: bool, reference_points=None, nuclides=None
    ):  # noqa: ANN001
        seen_rps.append(reference_points)
        return {
            "ok": True,
            "dry_run": dry_run,
            "steps": {
                "generate_inputs": {"ok": True, "generated_files": []},
                "run_mpi": {"ok": True, "completed": []},
                "extract_csv": {"ok": True, "csv_files": []},
                "plot_spectra": {"ok": True, "written_files": []},
            },
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr("mcnp_research_skill.batch.run_core_pipeline", fake_run_core_pipeline)

    result = run_batch_pipeline(_batch_config(base_file, output_dir), dry_run=True)

    assert result["ok"] is True
    for rp in seen_rps:
        assert rp is None
