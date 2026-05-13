"""MCNP MPI batch runner migrated from the legacy GUI workflow."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

TEMP_PATTERNS = ["runt*", "mesch*", "comou*", "mdata*", "i.txt", "o.txt"]


def _base_result(target_dir: str, mpi_command: str, dry_run: bool, confirm: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": dry_run,
        "confirm": confirm,
        "used_planned_inputs": False,
        "target_dir": target_dir,
        "mpi_command": mpi_command,
        "commands": [],
        "planned": [],
        "completed": [],
        "failed": [],
        "cleanup": [],
        "warnings": [],
        "errors": [],
    }


def _sanitize_filename(text: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", text.replace(" ", "").replace("(", "_").replace(")", ""))


def _numeric_input_files(target_path: Path) -> list[Path]:
    return sorted(
        [
            target_path / file_name
            for file_name in os.listdir(target_path)
            if file_name.endswith(".txt") and file_name[:-4].isdigit()
        ],
        key=lambda path: int(path.stem),
    )


def _reference_short_name(ref_text: str) -> str:
    if "铝壳" in ref_text or "閾濆３" in ref_text:
        return "铝壳表面"
    if "几何中心" in ref_text or "鍑犱綍涓績" in ref_text:
        return "几何中心"
    if "晶体" in ref_text or "鏅朵綋" in ref_text:
        return "晶体表面"
    return _sanitize_filename(ref_text)


def _metadata_from_input(input_path: Path) -> tuple[str, str, str, list[str]]:
    meta_id, dist_info, ref_short_name = "Unknown", "Data", "未知"
    warnings: list[str] = []

    try:
        content = input_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        warnings.append(f"Failed to read metadata from {input_path.name}: {exc}")
        return meta_id, dist_info, ref_short_name, warnings

    m_main = re.search(
        r"Meta_ID:\s*(.*?)\s*\|\s*(?:Distance|Dist):\s*(.*?)(?:\s*\||$)",
        content,
        flags=re.IGNORECASE,
    )
    if m_main:
        meta_id = _sanitize_filename(m_main.group(1))
        dist_info = m_main.group(2).strip()
    else:
        warnings.append(f"No Meta_ID/Dist metadata found in {input_path.name}")

    m_ref = re.search(r"Ref:\s*(.*?)(?:\s*\||\n|$)", content, flags=re.IGNORECASE)
    if m_ref:
        ref_short_name = _reference_short_name(m_ref.group(1))
    else:
        warnings.append(f"No Ref metadata found in {input_path.name}")

    return meta_id, dist_info, ref_short_name, warnings


def _unique_output_name(target_path: Path, base_final: str, reserved: set[str]) -> str:
    final_out = f"{base_final}.txt"
    counter = 1
    while (target_path / final_out).exists() or final_out in reserved:
        final_out = f"{base_final}_{counter}.txt"
        counter += 1
    reserved.add(final_out)
    return final_out


def _build_plan(target_path: Path, mpi_command: str, files_to_run: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    planned: list[dict[str, Any]] = []
    warnings: list[str] = []
    reserved_outputs: set[str] = set()

    for input_path in files_to_run:
        meta_id, dist_info, ref_short_name, meta_warnings = _metadata_from_input(input_path)
        warnings.extend(meta_warnings)
        base_final = f"{meta_id}-{dist_info}-{ref_short_name}"
        final_out = _unique_output_name(target_path, base_final, reserved_outputs)
        command = f"{mpi_command} i=i.txt o=o.txt"
        planned.append(
            {
                "input_file": input_path.name,
                "input_path": str(input_path),
                "output_file": final_out,
                "output_path": str(target_path / final_out),
                "meta_id": meta_id,
                "dist": dist_info,
                "ref": ref_short_name,
                "command": command,
            }
        )

    return planned, warnings


def _metadata_from_planned_input(entry: dict[str, Any]) -> tuple[str, str, str]:
    meta_id = _sanitize_filename(str(entry.get("meta_id") or Path(str(entry.get("path", "input.txt"))).stem))
    if "dist" in entry:
        dist_info = str(entry["dist"])
    elif "distance_cm" in entry:
        dist_info = f"{entry['distance_cm']}cm"
    else:
        dist_info = "Data"
    ref_short_name = _sanitize_filename(str(entry.get("reference_short") or entry.get("ref") or "planned"))
    return meta_id, dist_info, ref_short_name


def _build_plan_from_planned_inputs(
    target_path: Path,
    mpi_command: str,
    planned_input_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    reserved_outputs: set[str] = set()

    for entry in planned_input_files:
        input_path = Path(str(entry.get("path") or target_path / str(entry.get("file_name", "input.txt"))))
        input_file = str(entry.get("file_name") or input_path.name)
        meta_id, dist_info, ref_short_name = _metadata_from_planned_input(entry)
        base_final = f"{meta_id}-{dist_info}-{ref_short_name}"
        final_out = _unique_output_name(target_path, base_final, reserved_outputs)
        command = f"{mpi_command} i=i.txt o=o.txt"
        planned.append(
            {
                "input_file": input_file,
                "input_path": str(input_path),
                "output_file": final_out,
                "output_path": str(target_path / final_out),
                "meta_id": meta_id,
                "dist": dist_info,
                "ref": ref_short_name,
                "command": command,
            }
        )

    return planned


def _cleanup_temp_files(target_path: Path) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    warnings: list[str] = []
    for pattern in TEMP_PATTERNS:
        for file_path in glob.glob(str(target_path / pattern)):
            try:
                os.remove(file_path)
                removed.append(str(Path(file_path)))
            except OSError as exc:
                warnings.append(f"Failed to remove temporary file {file_path}: {exc}")
    return removed, warnings


def run_mpi_batch(
    target_dir: str,
    mpi_command: str,
    dry_run: bool = True,
    confirm: bool = False,
    cleanup_temp: bool = True,
    planned_input_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run numeric MCNP input files through an MPI command.

    Real execution is blocked unless ``dry_run=False`` and ``confirm=True``.
    """
    result = _base_result(target_dir, mpi_command, dry_run, confirm)

    if not dry_run and not confirm:
        result["errors"].append("confirm=True is required when dry_run=False")
        return result

    target_path = Path(target_dir)
    if dry_run and planned_input_files:
        planned = _build_plan_from_planned_inputs(target_path, mpi_command, planned_input_files)
        result["planned"] = planned
        result["commands"] = [item["command"] for item in planned]
        result["used_planned_inputs"] = True
        result["ok"] = bool(planned)
        return result

    if not target_path.exists() or not target_path.is_dir():
        result["errors"].append(f"target_dir does not exist or is not a directory: {target_dir}")
        return result

    try:
        files_to_run = _numeric_input_files(target_path)
    except OSError as exc:
        result["errors"].append(f"Failed to list target_dir: {exc}")
        return result

    if not files_to_run:
        result["warnings"].append("No numeric .txt input files were found")
        return result

    planned, warnings = _build_plan(target_path, mpi_command, files_to_run)
    result["planned"] = planned
    result["warnings"].extend(warnings)
    result["commands"] = [item["command"] for item in planned]

    if dry_run:
        result["ok"] = True
        return result

    success = False
    for item in planned:
        input_path = Path(item["input_path"])
        i_txt = target_path / "i.txt"
        o_txt = target_path / "o.txt"
        output_path = Path(item["output_path"])

        try:
            if o_txt.exists():
                o_txt.unlink()
            shutil.copyfile(input_path, i_txt)
            completed_process = subprocess.run(
                item["command"],
                shell=True,
                cwd=str(target_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            item["returncode"] = getattr(completed_process, "returncode", None)

            if o_txt.exists():
                os.rename(o_txt, output_path)
                result["completed"].append(item)
                success = True
            else:
                failed = dict(item)
                failed["error"] = "MCNP did not produce o.txt"
                result["failed"].append(failed)
        except Exception as exc:  # noqa: BLE001 - errors are reported structurally.
            failed = dict(item)
            failed["error"] = str(exc)
            result["failed"].append(failed)
        finally:
            if cleanup_temp:
                removed, cleanup_warnings = _cleanup_temp_files(target_path)
                result["cleanup"].extend(removed)
                result["warnings"].extend(cleanup_warnings)

    result["ok"] = success and not result["errors"]
    return result
