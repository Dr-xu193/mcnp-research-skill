"""Read-only diagnostics for local MCNP research pipeline configuration."""

from __future__ import annotations

import importlib.util
import os
import platform
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any


DEFAULT_REQUIRED_DEPENDENCIES = ("numpy", "pandas", "matplotlib", "scipy", "yaml")


def _check(name: str, ok: bool, detail: str, severity: str = "error") -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "severity": severity,
        "detail": detail,
    }


def _find_executable(command: str) -> tuple[bool, str]:
    if not command.strip():
        return False, "mpi_command is empty"

    try:
        parts = shlex.split(command, posix=False)
    except ValueError as exc:
        return False, f"mpi_command could not be parsed: {exc}"

    if not parts:
        return False, "mpi_command is empty"

    executable = parts[0].strip("\"'")
    if Path(executable).exists():
        return True, executable

    resolved = shutil.which(executable)
    if resolved:
        return True, resolved

    return False, f"Executable was not found on PATH or disk: {executable}"


def _nearest_existing_parent(path: Path) -> Path | None:
    current = path
    while not current.exists():
        if current.parent == current:
            return None
        current = current.parent
    return current


def run_doctor(
    config: dict[str, Any] | None = None,
    *,
    required_dependencies: tuple[str, ...] = DEFAULT_REQUIRED_DEPENDENCIES,
) -> dict[str, Any]:
    """Inspect environment and config without executing MCNP, Origin, or file writes."""
    config = config or {}
    result: dict[str, Any] = {
        "ok": True,
        "checks": [],
        "warnings": [],
        "errors": [],
        "recommendations": [],
    }

    checks: list[dict[str, Any]] = result["checks"]

    python_ok = sys.version_info >= (3, 10)
    checks.append(
        _check(
            "python_version",
            python_ok,
            f"{platform.python_implementation()} {platform.python_version()}",
        )
    )

    for dependency in required_dependencies:
        found = importlib.util.find_spec(dependency) is not None
        checks.append(_check(f"dependency_{dependency}", found, dependency))

    try:
        origin_available = (
            importlib.util.find_spec("pythoncom") is not None
            and importlib.util.find_spec("win32com.client") is not None
        )
    except (ImportError, ValueError):
        origin_available = False
    checks.append(
        _check(
            "origin_pywin32_available",
            origin_available,
            "pythoncom and win32com.client",
            severity="warning",
        )
    )
    if not origin_available:
        result["warnings"].append("pywin32 is not available; Origin export cannot execute on this environment")

    base_file_value = config.get("base_file")
    base_file = Path(str(base_file_value)) if base_file_value else None
    base_exists = bool(base_file and base_file.exists() and base_file.is_file())
    checks.append(
        _check(
            "base_file_exists",
            base_exists,
            str(base_file) if base_file else "base_file is missing from config",
        )
    )

    base_text = ""
    if base_exists and base_file is not None:
        try:
            base_text = base_file.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError as exc:
            checks.append(_check("base_file_readable", False, str(exc)))
        else:
            checks.append(_check("base_file_readable", True, str(base_file)))

    has_f8 = "f8:p,e" in base_text.lower()
    checks.append(_check("base_file_has_f8_tally", has_f8, "requires f8:p,e tally card"))

    has_nps = any(line.strip().lower().startswith("nps") for line in base_text.splitlines())
    checks.append(_check("base_file_has_nps", has_nps, "nps card is present or can be replaced"))

    output_dir_value = config.get("output_dir")
    output_dir = Path(str(output_dir_value)) if output_dir_value else None
    parent = _nearest_existing_parent(output_dir) if output_dir else None
    writable = bool(parent and os.access(parent, os.W_OK))
    checks.append(
        _check(
            "output_dir_parent_writable",
            writable,
            str(parent) if parent else "output_dir is missing or has no existing parent",
        )
    )

    mpi_command = str(config.get("mpi_command", ""))
    mpi_ok, mpi_detail = _find_executable(mpi_command)
    checks.append(_check("mpi_command_resolves", mpi_ok, mpi_detail))

    for check in checks:
        if check["ok"]:
            continue
        if check["severity"] == "warning":
            result["warnings"].append(check["detail"])
        else:
            result["errors"].append(f"{check['name']}: {check['detail']}")

    if result["errors"]:
        result["ok"] = False
        result["recommendations"].append("Fix error checks before executing MPI or batch workflows")
    if not mpi_ok:
        result["recommendations"].append("Use an absolute MPI executable path or add it to PATH")
    if not has_f8:
        result["recommendations"].append("Confirm the base MCNP deck contains an f8:p,e tally card")

    return result
