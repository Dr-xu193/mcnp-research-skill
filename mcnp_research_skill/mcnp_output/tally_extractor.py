"""MCNP tally CSV extraction migrated from the legacy GUI workflow."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any

CSV_HEADER = ["Energy (MeV)", "Tally (Counts/Particle)", "Relative Error"]
SKIPPED_TXT_NAMES = {"i.txt", "o.txt", "b.txt"}


def _base_result(target_dir: str, output_suffix: str, dry_run: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": dry_run,
        "target_dir": target_dir,
        "output_suffix": output_suffix,
        "count": 0,
        "csv_files": [],
        "planned_files": [],
        "processed_files": [],
        "warnings": [],
        "errors": [],
    }


def _candidate_txt_files(target_path: Path) -> list[Path]:
    return [
        target_path / file_name
        for file_name in os.listdir(target_path)
        if file_name.endswith(".txt")
        and not file_name.replace(".txt", "").isdigit()
        and file_name not in SKIPPED_TXT_NAMES
    ]


def _extract_rows(txt_path: Path) -> tuple[list[list[float]], bool]:
    lines = txt_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    data_rows: list[list[float]] = []
    in_tally = False
    found_energy_marker = False

    for line in lines:
        if re.search(r"^\s+energy\s*$", line, re.IGNORECASE):
            in_tally = True
            found_energy_marker = True
            continue

        if in_tally:
            parts = line.strip().split()
            if len(parts) == 3:
                try:
                    data_rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
                except ValueError:
                    break
            elif "total" in line.lower():
                break

    return data_rows, found_energy_marker


def extract_tally_csvs(
    target_dir: str,
    output_suffix: str = "_Data.csv",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Extract MCNP F8 tally tables into CSV files.

    This follows the legacy ``_core_extract_csv`` parsing behavior while
    returning structured results and supporting dry-run execution.
    """
    result = _base_result(target_dir, output_suffix, dry_run)
    target_path = Path(target_dir)

    if not target_path.exists() or not target_path.is_dir():
        result["errors"].append(f"target_dir does not exist or is not a directory: {target_dir}")
        return result

    for txt_path in _candidate_txt_files(target_path):
        try:
            rows, found_energy_marker = _extract_rows(txt_path)
        except OSError as exc:
            result["warnings"].append(f"Failed to read {txt_path.name}: {exc}")
            continue

        if not rows:
            if found_energy_marker:
                result["warnings"].append(f"No tally rows extracted from {txt_path.name}")
            else:
                result["warnings"].append(f"No energy tally marker found in {txt_path.name}")
            continue

        csv_path = txt_path.with_name(txt_path.stem + output_suffix)
        entry = {
            "txt_path": str(txt_path),
            "csv_path": str(csv_path),
            "row_count": len(rows),
            "rows": rows,
        }

        result["processed_files"].append(str(txt_path))

        if dry_run:
            result["planned_files"].append(entry)
        else:
            try:
                with csv_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(CSV_HEADER)
                    writer.writerows(rows)
            except OSError as exc:
                result["warnings"].append(f"Failed to write {csv_path.name}: {exc}")
                continue
            result["csv_files"].append(str(csv_path))

    result["count"] = len(result["planned_files"]) if dry_run else len(result["csv_files"])
    result["ok"] = result["count"] > 0 and not result["errors"]
    return result
