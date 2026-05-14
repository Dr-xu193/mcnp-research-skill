"""Workflow-level F8 postprocess adapter.

Calls existing ``_extract_rows`` (F8 CSV extraction) and
``plot_spectra`` (spectrum plotting), guarded by inspection to
ensure an F8 tally is present.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..mcnp_input.inspection import inspect_deck
from ..mcnp_output.tally_extractor import CSV_HEADER, _extract_rows
from ..spectra.plotter import plot_spectra

VALID_MODES = {"csv", "plot", "csv-and-plot"}


def postprocess_workflow(
    *,
    input_path: str | Path,
    work_dir: str | Path,
    mode: str = "csv",
    mcnp_output_path: str | Path | None = None,
    csv_output_path: str | Path | None = None,
    plot_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect deck → extract F8 CSV → (optional) plot."""

    in_path = Path(input_path)
    wd = Path(work_dir)
    wd.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "ok": False,
        "schema_version": "1.0",
        "mode": mode,
        "input_path": str(in_path),
        "artifacts": {},
        "blocked": [],
        "warnings": [],
        "errors": [],
    }

    # ---- validate mode ----
    if mode not in VALID_MODES:
        result["errors"].append(f"Invalid mode '{mode}'; must be one of {sorted(VALID_MODES)}")
        return result

    # ---- inspect deck ----
    try:
        text = in_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        result["errors"].append(str(exc))
        return result

    inspection = inspect_deck(text)
    tallies = inspection.get("tallies", [])
    has_f8 = any(t.get("kind") == "F8" for t in tallies)
    has_any = len(tallies) > 0

    result["inspection_summary"] = {
        "has_f8": has_f8,
        "geb_present": inspection.get("geb", {}).get("present", False),
    }

    if not has_any:
        result["blocked"].append({
            "code": "NO_SUPPORTED_TALLY_FOR_CSV",
            "message": "No tally cards found; CSV extraction / plotting requires F8.",
        })
        return result
    if not has_f8:
        result["blocked"].append({
            "code": "CSV_REQUIRES_F8",
            "message": "CSV extraction/plotting currently supports only F8 pulse-height tally.",
        })
        return result

    # ---- resolve mcnp output ----
    output_txt: Path
    if mcnp_output_path:
        output_txt = Path(mcnp_output_path)
    else:
        # Try to infer from work_dir
        candidates = sorted(wd.glob("*.txt"))
        candidates = [c for c in candidates if c.name not in ("i.txt", "o.txt", "b.txt")]
        if candidates:
            output_txt = candidates[0]
        else:
            result["errors"].append({
                "code": "MISSING_MCNP_OUTPUT",
                "message": "No MCNP output file provided and none found in work_dir.",
            })
            return result

    result["mcnp_output_path"] = str(output_txt)
    if not output_txt.exists():
        result["errors"].append({
            "code": "MISSING_MCNP_OUTPUT",
            "message": f"MCNP output file does not exist: {output_txt}",
        })
        return result

    csv_out = Path(csv_output_path) if csv_output_path else wd / "spectrum.csv"
    plot_out = Path(plot_output_path) if plot_output_path else wd / "spectrum.png"

    wants_csv = mode in ("csv", "csv-and-plot")
    wants_plot = mode in ("plot", "csv-and-plot")
    # Plot always needs CSV as input; generate it unconditionally when plotting
    needs_csv = wants_csv or wants_plot

    # ---- extract CSV ----
    if needs_csv:
        try:
            rows, _ = _extract_rows(output_txt)
        except Exception as exc:
            result["errors"].append({
                "code": "EXTRACT_FAILED",
                "message": str(exc),
            })
            return result

        if not rows:
            result["errors"].append({
                "code": "EXTRACT_FAILED",
                "message": "No tally rows extracted from MCNP output.",
            })
            return result

        try:
            with csv_out.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
                writer.writerows(rows)
        except OSError as exc:
            result["errors"].append({"code": "EXTRACT_FAILED", "message": str(exc)})
            return result

        result["artifacts"]["csv"] = str(csv_out)

    # ---- plot ----
    if wants_plot:
        try:
            plot_result = plot_spectra(
                csv_files=[str(csv_out)],
                output_path=str(plot_out),
                dry_run=False,
            )
        except Exception as exc:
            result["errors"].append({"code": "PLOT_FAILED", "message": str(exc)})
            return result

        if not plot_result.get("ok"):
            result["errors"].append({
                "code": "PLOT_FAILED",
                "message": "plot_spectra returned ok=false",
            })
            result["warnings"].extend(plot_result.get("warnings", []))
            return result

        result["artifacts"]["plot"] = str(plot_out)
        # If plot mode was requested without csv mode but required csv, note it
        if mode == "plot" and not wants_csv:
            result["artifacts"]["csv"] = str(csv_out)

    # ---- write manifest ----
    manifest_path = wd / "postprocess_manifest.json"
    try:
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["artifacts"]["postprocess_manifest_json"] = str(manifest_path)
    except OSError:
        pass

    result["ok"] = True
    return result
