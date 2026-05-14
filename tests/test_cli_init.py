"""CLI integration tests for ``mcnp-research init``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcnp_research_skill.cli import build_parser, main


# ---------------------------------------------------------------------------
# Parser smoke tests
# ---------------------------------------------------------------------------

def test_init_subparser_exists_and_accepts_flags():
    parser = build_parser()
    args = parser.parse_args(["init"])
    assert args.command == "init"
    assert args.force is False
    assert args.profile_name == "default"
    assert args.profile_path is None

    args2 = parser.parse_args(["init", "--force", "--profile", "lab2", "--path", "/tmp/p.yaml"])
    assert args2.force is True
    assert args2.profile_name == "lab2"
    assert args2.profile_path == "/tmp/p.yaml"


def test_init_does_not_require_config_flag():
    """init must not require --config (unlike most other subcommands)."""
    parser = build_parser()
    args = parser.parse_args(["init"])
    assert not hasattr(args, "config")


# ---------------------------------------------------------------------------
# Programmatic (main) tests
# ---------------------------------------------------------------------------

def test_init_creates_file_and_returns_json(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    result = main(["init", "--path", str(target)])
    assert result["ok"] is True
    assert result["created"] is True
    assert result["path"] == str(target)
    assert target.exists()


def test_init_without_force_rejects_existing_file(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text("old", encoding="utf-8")

    result = main(["init", "--path", str(target)])
    assert result["ok"] is False
    assert result["created"] is False
    assert result["reason"] == "already_exists"
    assert target.read_text(encoding="utf-8") == "old"


def test_init_with_force_overwrites_existing_file(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text("old", encoding="utf-8")

    result = main(["init", "--path", str(target), "--force"])
    assert result["ok"] is True
    assert result["created"] is True
    assert "active_profile:" in target.read_text(encoding="utf-8")


def test_init_respects_profile_flag(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    main(["init", "--path", str(target), "--profile", "lab2"])
    text = target.read_text(encoding="utf-8")
    assert "active_profile: lab2" in text


def test_init_default_path_is_home_dir():
    """The default behaviour writes to ~/.mcnp-research/profiles.yaml."""
    from mcnp_research_skill.config.profile import default_profile_path

    path = default_profile_path()
    assert path.parts[-1] == "profiles.yaml"
    assert ".mcnp-research" in str(path)


# ---------------------------------------------------------------------------
# Subprocess (real CLI entrypoint) tests
# ---------------------------------------------------------------------------

def test_cli_init_outputs_valid_json(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "init",
            "--path",
            str(target),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["created"] is True
    assert target.exists()


def test_cli_init_existing_file_returns_nonzero(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text("old", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "init",
            "--path",
            str(target),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["created"] is False


def test_cli_init_emits_ascii_safe_json(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "init",
            "--path",
            str(target),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Must be encodable as pure ASCII
    completed.stdout.encode("ascii")


def test_cli_init_profile_lab2_creates_real_profile(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcnp_research_skill.cli",
            "init",
            "--path",
            str(target),
            "--profile",
            "lab2",
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["active_profile"] == "lab2"
    assert target.exists()

    from mcnp_research_skill.config.profile import load_active_profile, load_profiles

    profiles = load_profiles(path=str(target))
    assert "lab2" in profiles["profiles"]
    lab2 = profiles["profiles"]["lab2"]
    assert lab2["mcnp"]["version"] == "mcnp5"
    assert lab2["detector"]["reference_points"]["crystal_center"]["z"] == 3.81

    # load_active_profile must succeed with lab2
    loaded = load_active_profile(path=str(target))
    assert loaded["mcnp"]["version"] == "mcnp5"

    loaded_explicit = load_active_profile(path=str(target), profile_name="lab2")
    assert loaded_explicit["mcnp"]["version"] == "mcnp5"


# ---------------------------------------------------------------------------
# Non-regression: init must not break existing subcommands
# ---------------------------------------------------------------------------

def test_init_does_not_break_other_subcommands():
    """Verify that adding init did not break parser dispatch for
    other commands.  This works entirely in-process."""
    # generate-inputs should still parse correctly
    import tempfile
    import os as _os

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "b.txt"
        base.write_text("e8 0 0.1\nf8:p,e 1\nnps 1\n", encoding="utf-8")
        config = Path(tmp) / "cfg.yaml"
        config.write_text(
            f'base_file: "{base.as_posix()}"\n'
            f'output_dir: "{(Path(tmp) / "work").as_posix()}"\n'
            'distance_cm: 20\n'
            'reference_point: "crystal_center"\n'
            'nps: "10000000"\n'
            "energies:\n  - 0.662\n"
            "composite_sources: []\n"
            "custom_energy: null\n"
            "geb_enabled: false\n"
            'mpi_command: "echo"\n'
            f'plot_output: "{(Path(tmp) / "work" / "s.png").as_posix()}"\n',
            encoding="utf-8",
        )
        result = main(["generate-inputs", "--config", str(config), "--dry-run"])
        assert result["ok"] is True
        assert result["dry_run"] is True
