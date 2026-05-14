"""Profile loading, merging, and persistence."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_PROFILE


def default_profile_path() -> Path:
    """Return the default profile file path."""
    return Path.home() / ".mcnp-research" / "profiles.yaml"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*.  Lists are replaced, not concatenated."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
    except ImportError:
        raise ImportError("PyYAML is required to read profiles — install with: python -m pip install PyYAML")
    if not isinstance(loaded, dict):
        raise ValueError(f"Profile file must be a YAML mapping: {path}")
    return loaded


def _dump_yaml(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        with path.open("w", encoding="utf-8") as handle:
            yaml.dump(
                data,
                handle,
                default_flow_style=False,
                allow_unicode=True,
                indent=2,
                sort_keys=False,
            )
    except ImportError:
        path.write_text(_manual_yaml_format(data), encoding="utf-8")


def _manual_yaml_format(data: Any, indent: int = 0) -> str:  # noqa: C901
    """Minimal YAML formatter — only used when PyYAML is unavailable."""
    prefix = "  " * indent
    lines: list[str] = []

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(_manual_yaml_format(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        inner = _manual_yaml_format(item, indent + 2)
                        lines.append(f"{prefix}  - {inner.lstrip()}")
                    else:
                        lines.append(f"{prefix}  - {_scalar(item)}")
            elif isinstance(value, bool):
                lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
            elif isinstance(value, str):
                lines.append(f'{prefix}{key}: {_quote_str(value)}')
            elif isinstance(value, float):
                lines.append(f"{prefix}{key}: {value}")
            elif isinstance(value, int):
                lines.append(f"{prefix}{key}: {value}")
            elif value is None:
                lines.append(f"{prefix}{key}: null")
            else:
                lines.append(f'{prefix}{key}: "{value}"')
    return "\n".join(lines)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _quote_str(value)
    if isinstance(value, float):
        return str(value)
    return str(value)


def _quote_str(value: str) -> str:
    if not value:
        return '""'
    return f'"{value}"'


def load_profiles(path: str | Path | None = None) -> dict[str, Any]:
    """Return the full profiles dictionary.

    Returns built-in defaults when no profiles file exists; merges user
    overrides on top of defaults when a file is present.
    """
    if path is None:
        path = default_profile_path()
    else:
        path = Path(path)

    if not path.exists() or not path.is_file():
        return copy.deepcopy(DEFAULT_PROFILE)

    user_data = _load_yaml(path)
    return deep_merge(copy.deepcopy(DEFAULT_PROFILE), user_data)


def load_active_profile(
    path: str | Path | None = None,
    profile_name: str | None = None,
) -> dict[str, Any]:
    """Return the active profile dict, user overrides merged onto defaults.

    When no profiles file exists the built-in ``default`` profile is returned
    without error.
    """
    profiles = load_profiles(path)

    active_name: str = profile_name or str(profiles.get("active_profile", "default"))
    all_profiles: dict[str, Any] = profiles.get("profiles", {})

    builtin_default = copy.deepcopy(DEFAULT_PROFILE["profiles"]["default"])

    if active_name not in all_profiles:
        return builtin_default

    return deep_merge(builtin_default, all_profiles[active_name])


def write_default_profiles(
    path: str | Path | None = None,
    force: bool = False,
    active_profile: str = "default",
) -> dict[str, Any]:
    """Write the default profiles YAML to *path*.

    CLI contract — always returns ``ok``, never raises on file-exists.
    """
    if path is None:
        target = default_profile_path()
    else:
        target = Path(path)

    if target.exists() and not force:
        return {
            "ok": False,
            "created": False,
            "path": str(target),
            "active_profile": active_profile,
            "reason": "already_exists",
            "warnings": [],
            "errors": [],
        }

    try:
        data = copy.deepcopy(DEFAULT_PROFILE)
        data["active_profile"] = active_profile
        _dump_yaml(data, target)
    except OSError as exc:
        return {
            "ok": False,
            "created": False,
            "path": str(target),
            "active_profile": active_profile,
            "reason": str(exc),
            "warnings": [],
            "errors": [str(exc)],
        }

    return {
        "ok": True,
        "created": True,
        "path": str(target),
        "active_profile": active_profile,
        "warnings": [],
        "errors": [],
    }


def expand_path(value: str, base_dir: str | Path | None = None) -> str:
    """Expand ``~``, env-vars, and resolve relative paths against *base_dir*.

    Returns *value* unchanged when it is not a non-empty string.
    """
    if not isinstance(value, str) or not value:
        return value

    expanded = os.path.expanduser(value)
    expanded = os.path.expandvars(expanded)
    p = Path(expanded)

    if not p.is_absolute() and base_dir is not None:
        p = Path(base_dir) / p

    return str(p)
