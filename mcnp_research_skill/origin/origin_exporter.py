"""Origin project export isolation layer."""

from __future__ import annotations

import glob
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


def _close_origin_app(origin_app: Any) -> dict[str, Any]:
    """Close or hide an Origin COM application object without changing export status."""
    result: dict[str, Any] = {"ok": False, "warnings": [], "errors": []}
    close_warnings: list[str] = []

    for method_name in ["Exit", "Quit"]:
        try:
            method = getattr(origin_app, method_name, None)
        except Exception as exc:  # noqa: BLE001
            close_warnings.append(f"Failed to access Origin {method_name}: {exc}")
            continue

        if callable(method):
            try:
                method()
                result["ok"] = True
                return result
            except Exception as exc:  # noqa: BLE001
                close_warnings.append(f"Origin {method_name}() failed: {exc}")

    try:
        origin_app.Visible = 0
        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        close_warnings.append(f"Failed to hide Origin window: {exc}")

    result["warnings"].append("Failed to close Origin cleanly: " + "; ".join(close_warnings))
    return result


def export_origin_projects(
    target_dir: str,
    csv_pattern: str = "*_Data.csv",
    temp_workspace: str = "C:/MCNP_Tmp",
    dry_run: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """Export Origin ``.opj`` projects from CSV files.

    Real Origin automation only runs when ``dry_run=False`` and
    ``confirm=True``. Dry-run mode only reports the planned CSV and OPJ paths.
    """
    result: dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "confirm": confirm,
        "target_dir": target_dir,
        "csv_pattern": csv_pattern,
        "temp_workspace": temp_workspace,
        "planned": [],
        "exported": [],
        "failed": [],
        "warnings": [],
        "errors": [],
    }

    target_path = Path(target_dir)
    if not target_path.exists() or not target_path.is_dir():
        result["errors"].append(f"target_dir does not exist or is not a directory: {target_dir}")
        return result

    csv_files = sorted(glob.glob(str(target_path / csv_pattern)))
    if not csv_files:
        result["warnings"].append(f"No CSV files matched pattern {csv_pattern}")
        return result

    for csv_path in csv_files:
        csv_file = Path(csv_path)
        result["planned"].append(
            {
                "csv_path": str(csv_file),
                "opj_path": str(target_path / f"{csv_file.stem}.opj"),
            }
        )

    if dry_run:
        result["ok"] = True
        return result

    if not confirm:
        result["errors"].append("confirm=True is required when dry_run=False")
        return result

    origin_app = None
    pythoncom = None
    temp_path = Path(temp_workspace)

    try:
        import pythoncom as pythoncom_module  # type: ignore
        import win32com.client  # type: ignore

        pythoncom = pythoncom_module
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"Origin COM dependencies are unavailable: {exc}")
        return result

    try:
        subprocess.run("taskkill /F /IM origin9.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run("taskkill /F /IM origin964.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0)

        temp_path.mkdir(parents=True, exist_ok=True)
        pythoncom.CoInitialize()
        origin_app = win32com.client.Dispatch("Origin.ApplicationSI")
        origin_app.Visible = 1

        for index, planned in enumerate(result["planned"]):
            csv_path = Path(planned["csv_path"])
            final_opj_path = Path(planned["opj_path"])
            safe_csv = temp_path / f"data_{index}.csv"
            safe_opj = temp_path / f"proj_{index}.opj"
            try:
                if final_opj_path.exists():
                    final_opj_path.unlink()
                shutil.copyfile(csv_path, safe_csv)
                origin_app.Execute("document -s; document -n;")
                time.sleep(0.5)
                origin_app.Execute(f'impCSV fname:="{str(safe_csv).replace(chr(92), "/")}";')
                time.sleep(1.0)
                origin_app.Execute("wks.col1.type = 4; wks.col2.type = 1; plotxy iy:=2 plot:=200;")
                time.sleep(0.8)
                origin_app.Execute("layer.x.type = 2; layer.y.type = 2; layer -a;")
                origin_app.Execute(f'page.longname$ = "{csv_path.stem}"; page.title = 1;')
                time.sleep(0.5)
                origin_app.Execute(f"save {safe_opj};")
                time.sleep(1.0)
                if safe_opj.exists():
                    shutil.copy2(safe_opj, final_opj_path)
                    result["exported"].append(planned)
                else:
                    result["failed"].append({**planned, "error": "Origin did not produce a temporary OPJ file"})
            except Exception as exc:  # noqa: BLE001
                result["failed"].append({**planned, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(str(exc))
    finally:
        if origin_app is not None:
            try:
                origin_app.Execute("document -s; document -n;")
                time.sleep(0.5)
            except Exception as exc:  # noqa: BLE001
                result["warnings"].append(f"Failed to reset Origin document before close: {exc}")
            close_result = _close_origin_app(origin_app)
            result["warnings"].extend(close_result.get("warnings", []))
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception as exc:  # noqa: BLE001
                result["warnings"].append(f"Failed to uninitialize COM: {exc}")
        try:
            if temp_path.exists():
                shutil.rmtree(temp_path)
        except Exception as exc:  # noqa: BLE001
            result["warnings"].append(f"Failed to remove temp_workspace: {exc}")

    result["ok"] = bool(result["exported"]) and not result["errors"]
    return result
