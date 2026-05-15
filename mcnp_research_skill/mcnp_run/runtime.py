"""Runtime preflight check and MPI command builder.

Checks the local environment for MCNP/MPI readiness without executing
anything.  Builds a recommended ``mpirun`` / ``mpiexec`` command line
from detected (or user-overridden) executables and processor count.
"""

from __future__ import annotations

import os
import shutil
from typing import Any


def _find_exe(candidates: list[str]) -> dict[str, Any]:
    """Search PATH and common locations for an executable."""
    for name in candidates:
        # Try bare name first
        path = shutil.which(name)
        if path:
            return {"found": True, "command": name, "path": str(path), "source": "PATH"}
        # Try with .exe suffix on Windows
        if os.name == "nt":
            path = shutil.which(name + ".exe")
            if path:
                return {"found": True, "command": name, "path": str(path), "source": "PATH"}
    return {"found": False, "command": candidates[0] if candidates else None, "path": None, "source": None}


def _find_mpi_launcher() -> dict[str, Any]:
    """Detect an MPI launcher (mpirun or mpiexec)."""
    return _find_exe(["mpirun", "mpiexec"])


def _find_mcnp_exe(mcnp_exe: str | None = None) -> dict[str, Any]:
    """Detect an MCNP executable."""
    if mcnp_exe:
        if os.path.isabs(mcnp_exe) and os.path.isfile(mcnp_exe):
            return {"found": True, "command": mcnp_exe, "path": mcnp_exe, "source": "user_override"}
        path = shutil.which(mcnp_exe)
        if path:
            return {"found": True, "command": mcnp_exe, "path": str(path), "source": "user_override"}
        return {"found": False, "command": mcnp_exe, "path": None, "source": "user_override_not_found"}
    return _find_exe(["mcnp5mpi", "mcnp5", "mcnp6", "mcnp"])


def run_runtime_check(
    *,
    np: int | None = None,
    mpi_launcher: str | None = None,
    mcnp_exe: str | None = None,
) -> dict[str, Any]:
    """Check the local environment for MCNP/MPI readiness.

    Parameters:
        np: Override recommended MPI process count.
        mpi_launcher: Override MPI launcher name/path.
        mcnp_exe: Override MCNP executable name/path.

    Returns a structured dict with ``can_execute_now``, ``command_preview``,
    and any errors found.
    """
    logical = os.cpu_count() or 1
    recommended_np = np or (logical + 1)
    np_policy = "user_override" if np is not None else "logical_processors_plus_one"

    errors: list[dict] = []
    warnings: list[dict] = []

    # ---- MPI launcher ----
    if mpi_launcher:
        mpi = _find_exe([mpi_launcher])
        if not mpi["found"]:
            errors.append({
                "code": "MPI_LAUNCHER_NOT_FOUND",
                "message": f"MPI launcher '{mpi_launcher}' not found on PATH.",
            })
    else:
        mpi = _find_mpi_launcher()
        if not mpi["found"]:
            errors.append({
                "code": "MPI_LAUNCHER_NOT_FOUND",
                "message": "No MPI launcher (mpirun/mpiexec) found on PATH.",
            })

    # ---- MCNP executable ----
    mcnp = _find_mcnp_exe(mcnp_exe)
    if not mcnp["found"]:
        errors.append({
            "code": "MCNP_NOT_FOUND",
            "message": (
                "MCNP executable not found.  Install a licensed MCNP "
                "distribution and ensure it is on PATH, or specify "
                "the full path with --mcnp-exe."
            ),
        })

    # ---- command preview ----
    can_execute = not errors
    command_preview: str | None = None
    if can_execute and mpi["command"] and mcnp["command"]:
        command_preview = f"{mpi['command']} -np {recommended_np} {mcnp['command']}"

    return {
        "ok": True,
        "logical_processors": logical,
        "recommended_np": recommended_np,
        "np_policy": np_policy,
        "mpi_launcher": mpi,
        "mcnp_executable": mcnp,
        "command_preview": command_preview,
        "can_execute_now": can_execute,
        "errors": errors,
        "warnings": warnings,
    }
