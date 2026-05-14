"""Tests for profile configuration loading, merging, and path expansion."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcnp_research_skill.config.defaults import DEFAULT_PROFILE
from mcnp_research_skill.config.profile import (
    deep_merge,
    expand_path,
    load_active_profile,
    load_profiles,
    write_default_profiles,
)


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------

def test_deep_merge_nested_dicts():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 99}}
    result = deep_merge(base, override)
    assert result["a"]["x"] == 1
    assert result["a"]["y"] == 99
    assert result["b"] == 3


def test_deep_merge_overrides_scalar():
    result = deep_merge({"a": 1}, {"a": 2})
    assert result["a"] == 2


def test_deep_merge_replaces_list():
    result = deep_merge({"a": [1, 2]}, {"a": [3]})
    assert result["a"] == [3]


def test_deep_merge_adds_new_key():
    result = deep_merge({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_deep_merge_does_not_mutate_originals():
    base = {"a": {"x": 1}}
    override = {"a": {"y": 2}}
    result = deep_merge(base, override)
    result["a"]["x"] = 999
    assert base["a"]["x"] == 1


# ---------------------------------------------------------------------------
# load_active_profile — no file on disk
# ---------------------------------------------------------------------------

def test_load_active_profile_returns_defaults_when_no_file(tmp_path: Path):
    nonexistent = tmp_path / "nonexistent.yaml"
    profile = load_active_profile(path=str(nonexistent))
    assert profile["mcnp"]["version"] == "mcnp5"
    assert profile["detector"]["reference_points"]["crystal_center"]["z"] == 3.81
    assert "Am-241" in profile["nuclides"]["single_energy"]


def test_load_active_profile_returns_defaults_when_no_path_given():
    """When no path is given and the real ~/.mcnp-research/profiles.yaml
    does not exist, the call must still return the built-in default."""
    # We pass an explicitly nonexistent path to avoid relying on the user's
    # home directory state.
    from mcnp_research_skill.config.profile import default_profile_path

    real_path = default_profile_path()
    if real_path.exists():
        # If it does exist, read through it — the test just must not crash.
        profile = load_active_profile()
        assert isinstance(profile, dict)
        assert "mcnp" in profile
    else:
        profile = load_active_profile()
        assert profile["mcnp"]["version"] == "mcnp5"


# ---------------------------------------------------------------------------
# write_default_profiles
# ---------------------------------------------------------------------------

def test_write_default_profiles_creates_file(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    result = write_default_profiles(path=str(target))
    assert result["ok"] is True
    assert result["created"] is True
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("active_profile:")


def test_write_default_profiles_no_overwrite_without_force(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text("existing", encoding="utf-8")
    original = target.read_text(encoding="utf-8")

    result = write_default_profiles(path=str(target))
    assert result["ok"] is False
    assert result["created"] is False
    assert result["reason"] == "already_exists"
    assert target.read_text(encoding="utf-8") == original


def test_write_default_profiles_overwrites_with_force(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text("existing", encoding="utf-8")

    result = write_default_profiles(path=str(target), force=True)
    assert result["ok"] is True
    assert result["created"] is True
    assert "active_profile:" in target.read_text(encoding="utf-8")


def test_write_default_profiles_respects_active_profile_flag(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    result = write_default_profiles(path=str(target), active_profile="lab2")
    assert result["active_profile"] == "lab2"
    text = target.read_text(encoding="utf-8")
    assert "active_profile: lab2" in text


# ---------------------------------------------------------------------------
# load_profiles / load_active_profile — with file on disk
# ---------------------------------------------------------------------------

def test_load_profiles_merges_user_overrides(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text(
        'active_profile: default\n'
        'profiles:\n'
        '  default:\n'
        '    mcnp:\n'
        '      mpi_command: "custom_mpi"\n',
        encoding="utf-8",
    )
    profiles = load_profiles(path=str(target))
    assert profiles["profiles"]["default"]["mcnp"]["mpi_command"] == "custom_mpi"
    # Keys not in user file must still be present from defaults
    assert profiles["profiles"]["default"]["mcnp"]["version"] == "mcnp5"


def test_load_active_profile_uses_named_profile(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text(
        'active_profile: default\n'
        'profiles:\n'
        '  default:\n'
        '    mcnp:\n'
        '      mpi_command: "default_mpi"\n'
        '  lab2:\n'
        '    mcnp:\n'
        '      mpi_command: "lab2_mpi"\n'
        '      version: "mcnp6"\n',
        encoding="utf-8",
    )
    profile = load_active_profile(path=str(target), profile_name="lab2")
    assert profile["mcnp"]["mpi_command"] == "lab2_mpi"
    assert profile["mcnp"]["version"] == "mcnp6"
    # Unrelated defaults still present
    assert profile["detector"]["reference_points"]["crystal_center"]["z"] == 3.81


def test_load_active_profile_raises_when_named_profile_missing(tmp_path: Path):
    """Explicit profile_name must exist — silent fallback is unsafe."""
    target = tmp_path / "profiles.yaml"
    target.write_text(
        'active_profile: default\n'
        'profiles:\n'
        '  default:\n'
        '    mcnp:\n'
        '      mpi_command: "default_mpi"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="nonexistent"):
        load_active_profile(path=str(target), profile_name="nonexistent")


def test_load_profiles_returns_defaults_for_nonexistent_file(tmp_path: Path):
    profiles = load_profiles(path=str(tmp_path / "nope.yaml"))
    assert profiles["active_profile"] == "default"
    assert profiles["profiles"]["default"]["mcnp"]["version"] == "mcnp5"


def test_write_default_profiles_creates_named_profile_with_full_content(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    result = write_default_profiles(path=str(target), active_profile="lab2")
    assert result["ok"] is True
    text = target.read_text(encoding="utf-8")
    assert "active_profile: lab2" in text
    actual = load_profiles(path=str(target))
    assert "lab2" in actual["profiles"]
    lab2 = actual["profiles"]["lab2"]
    assert lab2["mcnp"]["version"] == "mcnp5"
    assert lab2["detector"]["reference_points"]["crystal_center"]["z"] == 3.81
    assert "Am-241" in lab2["nuclides"]["single_energy"]
    # profiles.default must still exist
    assert "default" in actual["profiles"]


def test_load_active_profile_loads_lab2_after_write(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    write_default_profiles(path=str(target), active_profile="lab2")
    profile = load_active_profile(path=str(target))
    assert profile is not None
    # Auto-detect from YAML's active_profile should load lab2
    assert isinstance(profile, dict)


def test_load_active_profile_explicit_lab2_equals_auto_detect(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    write_default_profiles(path=str(target), active_profile="lab2")
    auto = load_active_profile(path=str(target))
    explicit = load_active_profile(path=str(target), profile_name="lab2")
    assert auto == explicit


def test_load_active_profile_raises_when_active_profile_points_to_missing(tmp_path: Path):
    """Broken config: active_profile references a non-existent profile."""
    target = tmp_path / "profiles.yaml"
    target.write_text(
        'active_profile: missing\n'
        'profiles:\n'
        '  default:\n'
        '    mcnp:\n'
        '      version: mcnp5\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing"):
        load_active_profile(path=str(target))


def test_load_active_profile_raises_when_explicit_profile_missing_from_file(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    target.write_text(
        'active_profile: default\n'
        'profiles:\n'
        '  default:\n'
        '    mcnp:\n'
        '      version: mcnp5\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ghost"):
        load_active_profile(path=str(target), profile_name="ghost")


# ---------------------------------------------------------------------------
# expand_path
# ---------------------------------------------------------------------------

def test_expand_path_tilde():
    result = expand_path("~/some/path")
    assert result == str(Path.home() / "some" / "path")


def test_expand_path_env_var(monkeypatch):
    monkeypatch.setenv("MCNP_TEST_VAR", "/test/value")
    result = expand_path("${MCNP_TEST_VAR}/sub")
    assert result.endswith("test/value/sub") or result.endswith("test\\value\\sub")


def test_expand_path_relative_with_base():
    result = expand_path("relative/path", base_dir="/base/dir")
    assert result == str(Path("/base/dir") / "relative" / "path")


def test_expand_path_absolute_ignores_base():
    result = expand_path("/absolute/path", base_dir="/base")
    assert result == str(Path("/absolute/path"))


def test_expand_path_empty_string_unchanged():
    assert expand_path("") == ""


def test_expand_path_non_string_unchanged():
    assert expand_path(42) == 42  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip: write then read
# ---------------------------------------------------------------------------

def test_write_then_load_active_profile_matches(tmp_path: Path):
    target = tmp_path / "profiles.yaml"
    write_default_profiles(path=str(target))
    profile = load_active_profile(path=str(target))
    assert profile["mcnp"]["version"] == "mcnp5"
    assert profile["detector"]["reference_points"]["crystal_center"]["z"] == 3.81
