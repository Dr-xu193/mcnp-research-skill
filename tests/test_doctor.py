from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.diagnostics import run_doctor


def _config(base_file: Path, output_dir: Path, mpi_command: str | None = None) -> dict[str, object]:
    return {
        "base_file": str(base_file),
        "output_dir": str(output_dir),
        "mpi_command": mpi_command or sys.executable,
    }


def test_doctor_passes_for_minimal_valid_local_config(tmp_path: Path) -> None:
    base_file = tmp_path / "base.txt"
    base_file.write_text("e8 0 0.1\nf8:p,e 1\nnps 100\n", encoding="utf-8")

    result = run_doctor(_config(base_file, tmp_path / "work"))

    assert result["ok"] is True
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["base_file_exists"]["ok"] is True
    assert checks["base_file_has_f8_tally"]["ok"] is True
    assert checks["base_file_has_nps"]["ok"] is True
    assert checks["mpi_command_resolves"]["ok"] is True


def test_doctor_reports_missing_base_file(tmp_path: Path) -> None:
    result = run_doctor(_config(tmp_path / "missing.txt", tmp_path / "work"))

    assert result["ok"] is False
    assert any("base_file" in error for error in result["errors"])


def test_doctor_reports_missing_required_dependency(monkeypatch, tmp_path: Path) -> None:
    base_file = tmp_path / "base.txt"
    base_file.write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")

    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None):
        if name == "pandas":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    result = run_doctor(_config(base_file, tmp_path / "work"), required_dependencies=("pandas",))

    assert result["ok"] is False
    assert any("pandas" in error for error in result["errors"])


def test_cli_doctor_outputs_json(tmp_path: Path) -> None:
    base_file = tmp_path / "base.txt"
    base_file.write_text("f8:p,e 1\nnps 100\n", encoding="utf-8")
    config_path = tmp_path / "pipeline.yaml"
    config_path.write_text(
        f"""base_file: "{base_file.as_posix()}"
output_dir: "{(tmp_path / 'work').as_posix()}"
mpi_command: "{sys.executable.replace(chr(92), '/')}"
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "doctor",
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
    assert payload["ok"] is True
    assert payload["checks"]
    assert completed.stderr == ""
