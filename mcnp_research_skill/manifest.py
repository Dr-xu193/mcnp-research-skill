"""Manifest helpers for reproducible MCNP research runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import csv
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


def _validation_check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _manifest_path(run_dir: str | Path | None, manifest_path: str | Path | None) -> Path:
    if manifest_path is not None:
        return Path(manifest_path)
    if run_dir is None:
        raise ValueError("Either run_dir or manifest_path is required")
    return Path(run_dir) / "manifest.json"


def _resolve_manifest_file(path_value: str, manifest_dir: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else manifest_dir / path


def _csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return 0
    return max(0, len([row for row in rows[1:] if any(cell.strip() for cell in row)]))


def _paths_from_step(step: dict[str, Any], list_key: str, path_key: str) -> list[str]:
    paths: list[str] = []
    for item in step.get(list_key, []):
        if isinstance(item, dict) and item.get(path_key):
            paths.append(str(item[path_key]))
        elif isinstance(item, str):
            paths.append(item)
    return paths


def validate_run(
    *,
    run_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a completed run manifest and its referenced artifacts."""
    result: dict[str, Any] = {
        "ok": False,
        "manifest_path": None,
        "checks": [],
        "summary": {
            "input_files": 0,
            "output_files": 0,
            "csv_files": 0,
            "csv_rows": 0,
            "png_files": 0,
        },
        "warnings": [],
        "errors": [],
    }

    try:
        path = _manifest_path(run_dir, manifest_path)
    except ValueError as exc:
        result["errors"].append(str(exc))
        return result

    result["manifest_path"] = str(path)
    checks: list[dict[str, Any]] = result["checks"]
    manifest_exists = path.exists() and path.is_file()
    checks.append(_validation_check("manifest_exists", manifest_exists, str(path)))
    if not manifest_exists:
        result["errors"].append(f"manifest.json was not found: {path}")
        return result

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(_validation_check("manifest_readable", False, str(exc)))
        result["errors"].append(str(exc))
        return result

    checks.append(_validation_check("manifest_readable", True, str(path)))
    manifest_errors = manifest.get("errors", [])
    manifest_clean = not manifest_errors
    checks.append(_validation_check("manifest_has_no_errors", manifest_clean, str(manifest_errors)))
    if manifest_errors:
        result["errors"].extend(str(error) for error in manifest_errors)

    manifest_dir = path.parent
    input_paths: list[Path] = []
    output_paths: list[Path] = []
    csv_paths: list[Path] = []
    png_paths: list[Path] = []

    for subrun in manifest.get("subruns", []):
        steps = subrun.get("result", {}).get("steps", {})
        input_paths.extend(
            _resolve_manifest_file(value, manifest_dir)
            for value in _paths_from_step(steps.get("generate_inputs", {}), "generated_files", "path")
        )
        output_paths.extend(
            _resolve_manifest_file(value, manifest_dir)
            for value in _paths_from_step(steps.get("run_mpi", {}), "completed", "output_path")
        )
        csv_paths.extend(
            _resolve_manifest_file(value, manifest_dir)
            for value in _paths_from_step(steps.get("extract_csv", {}), "csv_files", "path")
        )
        png_paths.extend(
            _resolve_manifest_file(value, manifest_dir)
            for value in _paths_from_step(steps.get("plot_spectra", {}), "written_files", "path")
        )

    for name, paths in [
        ("input_files_exist", input_paths),
        ("output_files_exist", output_paths),
        ("csv_files_exist", csv_paths),
        ("png_files_exist", png_paths),
    ]:
        ok = bool(paths) and all(item.exists() and item.is_file() for item in paths)
        checks.append(_validation_check(name, ok, f"{len(paths)} referenced"))
        if not ok:
            result["errors"].append(f"{name}: missing or empty reference set")

    csv_rows = 0
    csv_rows_ok = bool(csv_paths)
    for csv_path in csv_paths:
        try:
            row_count = _csv_row_count(csv_path)
        except OSError as exc:
            csv_rows_ok = False
            result["errors"].append(f"Failed to read CSV {csv_path}: {exc}")
            continue
        csv_rows += row_count
        if row_count <= 0:
            csv_rows_ok = False
            result["errors"].append(f"CSV has no data rows: {csv_path}")

    checks.append(_validation_check("csv_has_rows", csv_rows_ok, str(csv_rows)))
    result["summary"] = {
        "input_files": len(input_paths),
        "output_files": len(output_paths),
        "csv_files": len(csv_paths),
        "csv_rows": csv_rows,
        "png_files": len(png_paths),
    }

    result["ok"] = all(check["ok"] for check in checks) and not result["errors"]
    return result
