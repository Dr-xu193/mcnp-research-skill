from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.manifest import validate_run


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = PROJECT_ROOT / "tests" / "fixtures" / "golden"


def _write_complete_run(run_dir: Path) -> Path:
    distance_dir = run_dir / "distance_16.3cm"
    distance_dir.mkdir(parents=True)
    input_path = distance_dir / "1.txt"
    output_path = distance_dir / "result.txt"
    csv_path = distance_dir / "result_Data.csv"
    png_path = distance_dir / "spectra.png"

    input_path.write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")
    output_path.write_text((GOLDEN / "minimal_mcnp_output.txt").read_text(encoding="utf-8"), encoding="utf-8")
    csv_path.write_text((GOLDEN / "minimal_Data.csv").read_text(encoding="utf-8"), encoding="utf-8")
    png_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    manifest = {
        "schema_version": "0.2",
        "tool_version": "0.2.0",
        "dry_run": False,
        "errors": [],
        "warnings": [],
        "subruns": [
            {
                "distance_cm": 16.3,
                "result": {
                    "steps": {
                        "generate_inputs": {"generated_files": [{"path": str(input_path)}]},
                        "run_mpi": {"completed": [{"output_path": str(output_path)}]},
                        "extract_csv": {"csv_files": [str(csv_path)]},
                        "plot_spectra": {"written_files": [str(png_path)]},
                    }
                },
            }
        ],
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    return manifest_path


def test_validate_run_passes_complete_manifest(tmp_path: Path) -> None:
    _write_complete_run(tmp_path)

    result = validate_run(run_dir=str(tmp_path))

    assert result["ok"] is True
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["manifest_exists"]["ok"] is True
    assert checks["csv_has_rows"]["ok"] is True
    assert result["summary"]["csv_rows"] == 2


def test_validate_run_fails_when_manifest_missing(tmp_path: Path) -> None:
    result = validate_run(run_dir=str(tmp_path))

    assert result["ok"] is False
    assert any("manifest" in error.lower() for error in result["errors"])


def test_validate_run_fails_when_manifest_contains_errors(tmp_path: Path) -> None:
    manifest_path = _write_complete_run(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["errors"] = ["MPI failed"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_run(run_dir=str(tmp_path))

    assert result["ok"] is False
    assert any("MPI failed" in error for error in result["errors"])


def test_cli_validate_run_outputs_json(tmp_path: Path) -> None:
    _write_complete_run(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "validate-run",
            "--run-dir",
            str(tmp_path),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["summary"]["csv_rows"] == 2
    assert completed.stderr == ""
