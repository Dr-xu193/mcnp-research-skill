"""Manifest helpers for reproducible MCNP research runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


def sha256_file(path: str | Path) -> str | None:
    """Return SHA256 for an existing file, or None if it cannot be read."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def current_git_commit(repo_root: str | Path | None = None) -> str | None:
    """Return the current git commit hash if the repository is available."""
    cwd = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def build_manifest(
    *,
    config: dict[str, Any],
    dry_run: bool,
    subruns: list[dict[str, Any]],
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any]:
    """Build a JSON-serializable run manifest."""
    base_file = str(config.get("base_file", ""))
    return {
        "schema_version": "0.2",
        "tool_version": __version__,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_git_commit(),
        "dry_run": dry_run,
        "config": config,
        "base_file_sha256": sha256_file(base_file),
        "subruns": subruns,
        "warnings": warnings,
        "errors": errors,
    }


def write_manifest(manifest: dict[str, Any], manifest_path: str | Path) -> dict[str, Any]:
    """Write a manifest JSON file and return structured status."""
    path = Path(manifest_path)
    result: dict[str, Any] = {"ok": False, "path": str(path), "warnings": [], "errors": []}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        result["errors"].append(str(exc))
        return result
    result["ok"] = True
    return result
