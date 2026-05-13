from __future__ import annotations

import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_runtime_dependencies_and_console_script() -> None:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    dependencies = set(data["project"]["dependencies"])
    assert "numpy>=1.23" in dependencies
    assert "pandas>=1.5" in dependencies
    assert "matplotlib>=3.6" in dependencies
    assert "scipy>=1.10" in dependencies
    assert "PyYAML>=6.0" in dependencies

    optional = data["project"]["optional-dependencies"]
    assert "pywin32>=306" in optional["origin"]

    scripts = data["project"]["scripts"]
    assert scripts["mcnp-research"] == "mcnp_research_skill.cli:entrypoint"


def test_repository_hygiene_files_ignore_local_artifacts() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    gitattributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    for pattern in ["__pycache__/", ".pytest_cache/", "/A.txt", "*.opj", "runt*"]:
        assert pattern in gitignore

    assert "*.py text eol=lf" in gitattributes
    assert "*.md text eol=lf" in gitattributes
