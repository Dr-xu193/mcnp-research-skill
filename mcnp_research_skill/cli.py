"""Top-level command-line interface for the MCNP research pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .batch import run_batch_pipeline
from .config.profile import write_default_profiles
from .diagnostics import run_doctor
from .mcnp_input.inspection import inspect_deck_file
from .mcnp_input.patching import patch_deck_file
from .mcnp_input.diagnostics import diagnose_deck_file, repair_deck_file
from .models.registry import list_models, resolve_deck_path
from .workflow.planner import plan_workflow
from .workflow.batch import batch_workflow
from .workflow.postprocess import postprocess_workflow
from .workflow.prepare import prepare_workflow
from .workflow.run import run_workflow
from .workflow.sweep import prepare_disk_sweep, prepare_point_sweep, run_disk_sweep, run_point_sweep
from .mcnp_input.generator import generate_mcnp_inputs
from .mcnp_output.tally_extractor import extract_tally_csvs
from .mcnp_run.mpi_runner import run_mpi_batch
from .mcnp_run.runtime import run_runtime_check
from .workflow.nl_planner import plan_request
from .workflow.execute_plan import execute_plan
from .models.registry import get_model_reference_point
from .geb.spe import fit_geb_from_spe_files
from .origin.origin_exporter import export_origin_projects
from .manifest import validate_run
from .pipeline import run_core_pipeline
from .spectra.plotter import plot_spectra


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value == "[]":
        return []
    if value == "{}":
        return {}
    try:
        if any(char in value for char in [".", "e", "E"]):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_yaml_fallback(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        stripped = line.strip()
        if stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError("List item found without a preceding key")
            data.setdefault(current_list_key, []).append(_parse_scalar(stripped[2:]))
            continue

        current_list_key = None
        if ":" not in stripped:
            raise ValueError(f"Invalid config line: {raw_line}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = _parse_scalar(value)

    return data


def load_config(config_path: str) -> dict[str, Any]:
    """Load a YAML pipeline configuration."""
    text = Path(config_path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
    except ImportError:
        loaded = _load_yaml_fallback(text)

    if not isinstance(loaded, dict):
        raise ValueError("Pipeline config must be a mapping")
    return loaded


def _input_kwargs(config: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    return {
        "base_file": str(config["base_file"]),
        "output_dir": str(config["output_dir"]),
        "distance_cm": float(config["distance_cm"]),
        "reference_point": str(config["reference_point"]),
        "nps": str(config["nps"]),
        "energies": config.get("energies"),
        "composite_sources": config.get("composite_sources"),
        "custom_energy": config.get("custom_energy"),
        "geb_enabled": bool(config.get("geb_enabled", False)),
        "geb_params": config.get("geb_params"),
        "dry_run": dry_run,
    }


def _existing_csv_files(output_dir: str) -> list[str]:
    path = Path(output_dir)
    if not path.exists() or not path.is_dir():
        return []
    return [str(csv_path) for csv_path in sorted(path.glob("*_Data.csv")) if csv_path.is_file()]


def _resolve_input(args: argparse.Namespace) -> str:
    """Return the resolved input path: ``--builtin-model`` takes precedence over ``--input``."""
    bi = getattr(args, "builtin_model", None)
    inp = getattr(args, "input", None)
    if bi and inp:
        return "__INPUT_CONFLICT__"
    if bi:
        return str(resolve_deck_path(bi))
    if not inp:
        return ""
    return str(inp)


def _resolve_sweep_reference(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve ``--reference-point`` or ``--reference-position`` for sweep commands.

    Returns ``{"ok": True, "reference_position": [...], ...}`` or
    ``{"ok": False, "errors": [...]}``.
    """
    rp_name = getattr(args, "reference_point", None)
    r_pos = getattr(args, "reference_position", None)
    if rp_name and r_pos and r_pos != (0, 0, 0):
        return {"ok": False, "errors": [{"code": "REFERENCE_POSITION_CONFLICT",
            "message": "不能同时指定 --reference-point 和 --reference-position。请二选一。"}]}
    if rp_name:
        bi = getattr(args, "builtin_model", None)
        inp = getattr(args, "input", None)
        model_id = bi
        if not model_id:
            return {"ok": False, "errors": [{"code": "MISSING_BUILTIN_MODEL",
                "message": "--reference-point 需要配合 --builtin-model 使用。"}]}
        result = get_model_reference_point(model_id, rp_name)
        if not result.get("ok"):
            return result
        return {"ok": True, "reference_position": result["position"],
                "reference_point_meta": result}
    if r_pos is None:
        r_pos = (0, 0, 0)
    return {"ok": True, "reference_position": list(r_pos)}


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    """Execute a parsed CLI command and return a structured result."""
    if args.command == "init":
        return write_default_profiles(
            path=args.profile_path,
            force=bool(args.force),
            active_profile=str(args.profile_name),
        )

    if args.command == "plan-request":
        text = ""
        if getattr(args, "text", None):
            text = args.text
        elif getattr(args, "text_file", None):
            text = Path(args.text_file).read_text(encoding="utf-8")
        if not text.strip():
            return {"ok": False, "errors": [{"code": "MISSING_REQUEST_TEXT", "message": "Provide --text or --text-file."}]}
        plan = plan_request(
            text,
            np=getattr(args, "np", None),
            mpi_launcher=getattr(args, "mpi_launcher", None),
            mcnp_exe=getattr(args, "mcnp_exe", None),
        )
        output = getattr(args, "output", None)
        if output:
            import json as _json
            Path(output).write_text(_json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return plan

    if args.command == "execute-plan":
        plan_file = getattr(args, "plan_file", None)
        if not plan_file:
            return {"ok": False, "errors": [{"code": "PLAN_FILE_NOT_FOUND", "message": "--plan-file is required."}]}
        pf = Path(plan_file)
        if not pf.is_file():
            return {"ok": False, "errors": [{"code": "PLAN_FILE_NOT_FOUND", "message": f"Plan file not found: {plan_file}"}]}
        try:
            import json as _json
            plan = _json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            return {"ok": False, "errors": [{"code": "PLAN_FILE_INVALID", "message": f"Failed to parse JSON from {plan_file}"}]}
        return execute_plan(
            plan,
            execute=not bool(getattr(args, "dry_run", True)),
            confirm_user=bool(getattr(args, "confirm_user", False)),
            np=getattr(args, "np", None),
            mpi_launcher=getattr(args, "mpi_launcher", None),
            mcnp_exe=getattr(args, "mcnp_exe", None),
            mpi_command=getattr(args, "mpi_command", None),
            work_dir=getattr(args, "work_dir", None),
        )

    if args.command == "runtime-check":
        return run_runtime_check(
            np=getattr(args, "np", None),
            mpi_launcher=getattr(args, "mpi_launcher", None),
            mcnp_exe=getattr(args, "mcnp_exe", None),
        )

    if args.command == "models":
        if args.models_action == "list":
            return {"ok": True, "models": list_models()}
        if args.models_action == "inspect":
            try:
                path = str(resolve_deck_path(args.model_id))
            except (ValueError, FileNotFoundError) as exc:
                return {"ok": False, "errors": [{"code": "MODEL_NOT_FOUND", "message": str(exc)}]}
            return inspect_deck_file(path)
        return {"ok": False, "errors": [{"code": "INVALID_MODELS_ACTION", "message": f"Unknown models action: {args.models_action}"}]}

    if args.command == "diagnose-deck":
        diag_input = _resolve_input(args)
        if not diag_input:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "--input or --builtin-model is required."}]}
        mv = getattr(args, "mcnp_version", "mcnp5_rsicc_1_14")
        return diagnose_deck_file(diag_input, mcnp_version=mv)

    if args.command == "repair-deck":
        repair_input = _resolve_input(args)
        if not repair_input:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "--input or --builtin-model is required."}]}
        if not getattr(args, "output", None):
            return {"ok": False, "errors": [{"code": "MISSING_OUTPUT", "message": "--output is required for repair-deck."}]}
        mv = getattr(args, "mcnp_version", "mcnp5_rsicc_1_14")
        return repair_deck_file(repair_input, args.output, mcnp_version=mv)

    if args.command == "inspect-deck":
        input_path = _resolve_input(args)
        if not input_path:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "Either --input or --builtin-model is required."}]}
        result = inspect_deck_file(input_path)
        if getattr(args, "diagnostics", False):
            mv = getattr(args, "mcnp_version", "mcnp5_rsicc_1_14")
            result["diagnostics"] = diagnose_deck_file(input_path, mcnp_version=mv)
        return result

    if args.command == "plan-workflow":
        input_path = _resolve_input(args)
        if not input_path:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "Either --input or --builtin-model is required."}]}
        inspection = inspect_deck_file(input_path)
        if not inspection.get("ok"):
            return inspection
        return plan_workflow(
            inspection,
            workflow_mode=args.workflow_mode,
            source_strategy=getattr(args, "source_strategy", None),
            postprocess=getattr(args, "postprocess", "none"),
            requested_nps=getattr(args, "nps", None),
        )

    if args.command == "patch-deck":
        input_path = _resolve_input(args)
        if not input_path:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "Either --input or --builtin-model is required."}]}
        sp = getattr(args, "source_position", None)
        if sp is not None:
            sp = [float(v) for v in sp]
        result = patch_deck_file(
            input_path, args.output,
            nps=getattr(args, "nps", None),
            source_strategy=getattr(args, "source_strategy", "preserve_existing_source"),
            source_position=sp,
            source_energy=getattr(args, "source_energy", None),
            source_particle=getattr(args, "source_particle", None),
            source_radius=getattr(args, "source_radius", None),
            source_ext=getattr(args, "source_ext", 0),
            source_card_id=getattr(args, "source_card_id", None),
        )
        result.pop("text", None)
        return result

    if args.command == "prepare-workflow":
        input_path = _resolve_input(args)
        if not input_path:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "Either --input or --builtin-model is required."}]}
        if getattr(args, "diagnostics", False) or getattr(args, "mcnp_version", None):
            mv = getattr(args, "mcnp_version", "mcnp5_rsicc_1_14")
            diag = diagnose_deck_file(input_path, mcnp_version=mv)
            if not diag.get("ok"):
                diag["stage"] = "diagnostics"
                return diag
        return prepare_workflow(
            input_path=input_path,
            work_dir=args.work_dir,
            workflow_mode=args.workflow_mode,
            source_strategy=getattr(args, "source_strategy", None),
            postprocess=getattr(args, "postprocess", "none"),
            nps=getattr(args, "nps", None),
            source_position=getattr(args, "source_position", None),
            source_energy=getattr(args, "source_energy", None),
            source_particle=getattr(args, "source_particle", None),
            source_radius=getattr(args, "source_radius", None),
            source_ext=getattr(args, "source_ext", 0),
            source_card_id=getattr(args, "source_card_id", None),
        )

    if args.command == "batch-workflow":
        return batch_workflow(
            input_dir=args.input_dir,
            work_dir=args.work_dir,
            workflow_mode=args.workflow_mode,
            source_strategy=getattr(args, "source_strategy", None),
            postprocess=getattr(args, "postprocess", "none"),
            nps=getattr(args, "nps", None),
            input_files=getattr(args, "input_files", None),
            mpi_config_path=getattr(args, "mpi_config", None),
            execute=not bool(getattr(args, "dry_run", True)),
            confirm_mpi=bool(getattr(args, "confirm_mpi", False)),
            mcnp_outputs=getattr(args, "mcnp_outputs", None),
            csv_dir=getattr(args, "csv_dir", None),
            plot_dir=getattr(args, "plot_dir", None),
        )

    if args.command == "run-workflow":
        input_path = _resolve_input(args)
        if not input_path:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT", "message": "Either --input or --builtin-model is required."}]}
        mpi_cfg = getattr(args, "mpi_config", None)
        mpi_cmd: str | None = None
        if mpi_cfg is not None and not getattr(args, "dry_run", True):
            try:
                cfg = load_config(str(mpi_cfg))
                mpi_cmd = str(cfg.get("mpi_command", ""))
            except Exception as exc:
                return {"ok": False, "errors": [str(exc)], "warnings": []}
        return run_workflow(
            input_path=input_path,
            work_dir=args.work_dir,
            workflow_mode=args.workflow_mode,
            source_strategy=getattr(args, "source_strategy", None),
            postprocess=getattr(args, "postprocess", "none"),
            nps=getattr(args, "nps", None),
            mpi_command=mpi_cmd,
            execute=not bool(getattr(args, "dry_run", True)),
            confirm_mpi=bool(getattr(args, "confirm_mpi", False)),
            mcnp_output_path=getattr(args, "mcnp_output", None),
            csv_output_path=getattr(args, "csv_output", None),
            plot_output_path=getattr(args, "plot_output", None),
            source_position=getattr(args, "source_position", None),
            source_energy=getattr(args, "source_energy", None),
            source_particle=getattr(args, "source_particle", None),
            source_radius=getattr(args, "source_radius", None),
            source_ext=getattr(args, "source_ext", 0),
            source_card_id=getattr(args, "source_card_id", None),
        )

    if args.command == "run-point-sweep":
        sweep_input = _resolve_input(args)
        if sweep_input == "__INPUT_CONFLICT__":
            return {"ok": False, "errors": [{"code": "INPUT_CONFLICT",
                "message": "不能同时指定 --input 和 --builtin-model。请二选一。"}]}
        if not sweep_input:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT",
                "message": "Either --input or --builtin-model is required."}]}
        rp = _resolve_sweep_reference(args)
        if not rp["ok"]:
            return rp
        return run_point_sweep(
            input_path=sweep_input,
            work_dir=args.work_dir,
            distances=getattr(args, "distances", None),
            start=getattr(args, "start", None),
            stop=getattr(args, "stop", None),
            step=getattr(args, "step", None),
            axis=getattr(args, "axis", "z"),
            reference_position=rp["reference_position"],
            direction=getattr(args, "direction", 1),
            source_energy=args.source_energy,
            source_particle=getattr(args, "source_particle", None),
            nps=getattr(args, "nps", None),
            postprocess=getattr(args, "postprocess", "none"),
            mpi_config_path=getattr(args, "mpi_config", None),
            execute=not bool(getattr(args, "dry_run", True)),
            confirm_mpi=bool(getattr(args, "confirm_mpi", False)),
            mcnp_outputs=getattr(args, "mcnp_outputs", None),
            csv_dir=getattr(args, "csv_dir", None),
            plot_dir=getattr(args, "plot_dir", None),
        )

    if args.command == "run-disk-sweep":
        sweep_input = _resolve_input(args)
        if sweep_input == "__INPUT_CONFLICT__":
            return {"ok": False, "errors": [{"code": "INPUT_CONFLICT",
                "message": "不能同时指定 --input 和 --builtin-model。请二选一。"}]}
        if not sweep_input:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT",
                "message": "Either --input or --builtin-model is required."}]}
        rp = _resolve_sweep_reference(args)
        if not rp["ok"]:
            return rp
        return run_disk_sweep(
            input_path=sweep_input, work_dir=args.work_dir,
            distances=getattr(args, "distances", None),
            start=getattr(args, "start", None), stop=getattr(args, "stop", None), step=getattr(args, "step", None),
            axis=getattr(args, "axis", "z"), reference_position=rp["reference_position"],
            direction=getattr(args, "direction", 1),
            source_energy=args.source_energy, source_radius=args.source_radius,
            source_particle=getattr(args, "source_particle", None),
            source_ext=getattr(args, "source_ext", 0), source_card_id=getattr(args, "source_card_id", None),
            nps=getattr(args, "nps", None), postprocess=getattr(args, "postprocess", "none"),
            mpi_config_path=getattr(args, "mpi_config", None),
            execute=not bool(getattr(args, "dry_run", True)),
            confirm_mpi=bool(getattr(args, "confirm_mpi", False)),
            mcnp_outputs=getattr(args, "mcnp_outputs", None),
            csv_dir=getattr(args, "csv_dir", None), plot_dir=getattr(args, "plot_dir", None),
        )

    if args.command == "prepare-disk-sweep":
        sweep_input = _resolve_input(args)
        if sweep_input == "__INPUT_CONFLICT__":
            return {"ok": False, "errors": [{"code": "INPUT_CONFLICT",
                "message": "不能同时指定 --input 和 --builtin-model。请二选一。"}]}
        if not sweep_input:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT",
                "message": "Either --input or --builtin-model is required."}]}
        rp = _resolve_sweep_reference(args)
        if not rp["ok"]:
            return rp
        return prepare_disk_sweep(
            input_path=sweep_input, work_dir=args.work_dir,
            distances=getattr(args, "distances", None),
            start=getattr(args, "start", None), stop=getattr(args, "stop", None), step=getattr(args, "step", None),
            axis=getattr(args, "axis", "z"), reference_position=rp["reference_position"],
            direction=getattr(args, "direction", 1),
            source_energy=args.source_energy, source_radius=args.source_radius,
            source_particle=getattr(args, "source_particle", None),
            source_ext=getattr(args, "source_ext", 0), source_card_id=getattr(args, "source_card_id", None),
            nps=getattr(args, "nps", None), postprocess=getattr(args, "postprocess", "none"),
        )

    if args.command == "prepare-point-sweep":
        sweep_input = _resolve_input(args)
        if sweep_input == "__INPUT_CONFLICT__":
            return {"ok": False, "errors": [{"code": "INPUT_CONFLICT",
                "message": "不能同时指定 --input 和 --builtin-model。请二选一。"}]}
        if not sweep_input:
            return {"ok": False, "errors": [{"code": "MISSING_INPUT",
                "message": "Either --input or --builtin-model is required."}]}
        rp = _resolve_sweep_reference(args)
        if not rp["ok"]:
            return rp
        return prepare_point_sweep(
            input_path=sweep_input,
            work_dir=args.work_dir,
            distances=getattr(args, "distances", None),
            start=getattr(args, "start", None),
            stop=getattr(args, "stop", None),
            step=getattr(args, "step", None),
            axis=getattr(args, "axis", "z"),
            reference_position=rp["reference_position"],
            direction=getattr(args, "direction", 1),
            source_energy=args.source_energy,
            source_particle=getattr(args, "source_particle", None),
            nps=getattr(args, "nps", None),
            postprocess=getattr(args, "postprocess", "none"),
        )

    if args.command == "postprocess-workflow":
        return postprocess_workflow(
            input_path=args.input,
            work_dir=args.work_dir,
            mode=args.mode,
            mcnp_output_path=getattr(args, "mcnp_output", None),
            csv_output_path=getattr(args, "csv_output", None),
            plot_output_path=getattr(args, "plot_output", None),
        )

    if args.command == "fit-geb-from-spe":
        kwargs_spe: dict[str, Any] = {"spe_files": args.spe_files}
        pp = getattr(args, "profile_path", None)
        pn = getattr(args, "profile_name", None)
        if pp or pn:
            from .config.profile import load_active_profile
            from .geb.spe import _merge_geb_nuclides

            active = load_active_profile(path=pp, profile_name=pn)
            geb = active.get("geb", {})
            nuclide_energies_dict, _ = _merge_geb_nuclides(geb)
            kwargs_spe["nuclide_energies"] = nuclide_energies_dict
        return fit_geb_from_spe_files(**kwargs_spe)

    if args.command == "origin-export":
        return export_origin_projects(
            target_dir=str(args.target_dir),
            csv_pattern=str(args.csv_pattern),
            temp_workspace=str(args.temp_workspace),
            dry_run=bool(args.dry_run),
            confirm=bool(args.confirm_origin),
        )

    if args.command == "batch-run":
        geb_params = None
        if args.geb is not None:
            geb_params = {"a": args.geb[0], "b": args.geb[1], "c": args.geb[2]}
        config = {
            "base_file": str(args.base_file),
            "output_dir": str(args.output_dir),
            "reference_point": str(args.reference_point),
            "nps": str(args.nps),
            "distance_start": float(args.distance_start),
            "distance_end": float(args.distance_end),
            "distance_step": float(args.distance_step),
            "custom_energy_kev": float(args.custom_energy_kev),
            "geb_enabled": args.geb is not None,
            "geb_params": geb_params,
            "mpi_command": str(args.mpi_command),
        }
        kwargs_batch: dict[str, Any] = {
            "dry_run": bool(args.dry_run),
            "confirm_mpi": bool(args.confirm_mpi),
        }
        pp = getattr(args, "profile_path", None)
        pn = getattr(args, "profile_name", None)
        if pp or pn:
            from .config.profile import load_active_profile

            active = load_active_profile(path=pp, profile_name=pn)
            kwargs_batch["reference_points"] = active.get("detector", {}).get("reference_points", {})
            kwargs_batch["nuclides"] = active.get("nuclides")
        return run_batch_pipeline(config, **kwargs_batch)

    if args.command == "validate-run":
        return validate_run(run_dir=args.run_dir, manifest_path=args.manifest)

    config = load_config(args.config)
    dry_run = bool(args.dry_run)

    if args.command == "doctor":
        return run_doctor(config)

    if args.command == "generate-inputs":
        kwargs = _input_kwargs(config, dry_run)
        profile_path = getattr(args, "profile_path", None)
        profile_name = getattr(args, "profile_name", None)
        if profile_path or profile_name:
            from .config.profile import load_active_profile

            active = load_active_profile(path=profile_path, profile_name=profile_name)
            kwargs["reference_points"] = active.get("detector", {}).get("reference_points", {})
            kwargs["nuclides"] = active.get("nuclides")
        return generate_mcnp_inputs(**kwargs)

    if args.command == "run-mpi":
        return run_mpi_batch(
            target_dir=str(config["output_dir"]),
            mpi_command=str(config["mpi_command"]),
            dry_run=dry_run,
            confirm=bool(args.confirm_mpi),
            input_files=getattr(args, "input_files", None),
        )

    if args.command == "extract-csv":
        return extract_tally_csvs(target_dir=str(config["output_dir"]), dry_run=dry_run)

    if args.command == "plot-spectra":
        csv_files = _existing_csv_files(str(config["output_dir"]))
        if not csv_files:
            return {
                "ok": False,
                "dry_run": dry_run,
                "csv_files": [],
                "warnings": ["No *_Data.csv files found for plotting"],
                "errors": [],
            }
        return plot_spectra(
            csv_files=csv_files,
            output_path=str(config["plot_output"]),
            dry_run=dry_run,
        )

    if args.command == "run-core-pipeline":
        kwargs: dict[str, Any] = {
            "dry_run": dry_run,
            "confirm_mpi": bool(args.confirm_mpi),
        }
        pp = getattr(args, "profile_path", None)
        pn = getattr(args, "profile_name", None)
        if pp or pn:
            from .config.profile import load_active_profile

            active = load_active_profile(path=pp, profile_name=pn)
            kwargs["reference_points"] = active.get("detector", {}).get("reference_points", {})
            kwargs["nuclides"] = active.get("nuclides")
        return run_core_pipeline(config, **kwargs)

    return {"ok": False, "errors": [f"Unsupported command: {args.command}"], "warnings": []}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mcnp_research_skill.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--force", action="store_true", default=False)
    init_parser.add_argument("--profile", default="default", dest="profile_name")
    init_parser.add_argument("--path", default=None, dest="profile_path")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config", required=True)
    doctor_parser.set_defaults(dry_run=True)

    gen_parser = subparsers.add_parser("generate-inputs")
    gen_parser.add_argument("--config", required=True)
    gen_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    gen_parser.add_argument("--execute", action="store_false", dest="dry_run")
    gen_parser.add_argument("--profile-path", default=None)
    gen_parser.add_argument("--profile-name", default=None)

    pipeline_parser = subparsers.add_parser("run-core-pipeline")
    pipeline_parser.add_argument("--config", required=True)
    pipeline_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    pipeline_parser.add_argument("--execute", action="store_false", dest="dry_run")
    pipeline_parser.add_argument("--confirm-mpi", action="store_true", default=False)
    pipeline_parser.add_argument("--profile-path", default=None)
    pipeline_parser.add_argument("--profile-name", default=None)

    mpi_parser = subparsers.add_parser("run-mpi")
    mpi_parser.add_argument("--config", required=True)
    mpi_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    mpi_parser.add_argument("--execute", action="store_false", dest="dry_run")
    mpi_parser.add_argument("--confirm-mpi", action="store_true", default=False)
    mpi_parser.add_argument("--input-files", nargs="*", default=None, dest="input_files")

    for command in ["extract-csv", "plot-spectra"]:
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", required=True)
        subparser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
        subparser.add_argument("--execute", action="store_false", dest="dry_run")

    plan_req_parser = subparsers.add_parser("plan-request")
    plan_req_parser.add_argument("--text", default=None, dest="text")
    plan_req_parser.add_argument("--text-file", default=None, dest="text_file")
    plan_req_parser.add_argument("--np", type=int, default=None, dest="np")
    plan_req_parser.add_argument("--mpi-launcher", default=None, dest="mpi_launcher")
    plan_req_parser.add_argument("--mcnp-exe", default=None, dest="mcnp_exe")
    plan_req_parser.add_argument("--output", default=None, dest="output")

    exec_parser = subparsers.add_parser("execute-plan")
    exec_parser.add_argument("--plan-file", required=True, dest="plan_file")
    exec_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    exec_parser.add_argument("--execute", action="store_false", dest="dry_run")
    exec_parser.add_argument("--confirm-user", action="store_true", default=False, dest="confirm_user")
    exec_parser.add_argument("--np", type=int, default=None, dest="np")
    exec_parser.add_argument("--mpi-launcher", default=None, dest="mpi_launcher")
    exec_parser.add_argument("--mcnp-exe", default=None, dest="mcnp_exe")
    exec_parser.add_argument("--mpi-command", default=None, dest="mpi_command")
    exec_parser.add_argument("--work-dir", default=None, dest="work_dir")

    runtime_parser = subparsers.add_parser("runtime-check")
    runtime_parser.add_argument("--np", type=int, default=None, dest="np")
    runtime_parser.add_argument("--mpi-launcher", default=None, dest="mpi_launcher")
    runtime_parser.add_argument("--mcnp-exe", default=None, dest="mcnp_exe")

    models_parser = subparsers.add_parser("models")
    models_parser.add_argument("models_action", choices=["list", "inspect"])
    models_parser.add_argument("model_id", nargs="?", default=None)

    diag_parser = subparsers.add_parser("diagnose-deck")
    diag_parser.add_argument("--input", default=None, dest="input")
    diag_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    diag_parser.add_argument("--mcnp-version", default="mcnp5_rsicc_1_14", dest="mcnp_version")

    repair_parser = subparsers.add_parser("repair-deck")
    repair_parser.add_argument("--input", default=None, dest="input")
    repair_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    repair_parser.add_argument("--output", required=True, dest="output")
    repair_parser.add_argument("--mcnp-version", default="mcnp5_rsicc_1_14", dest="mcnp_version")

    inspect_parser = subparsers.add_parser("inspect-deck")
    inspect_parser.add_argument("--input", default=None, dest="input")
    inspect_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    inspect_parser.add_argument("--diagnostics", action="store_true", default=False, dest="diagnostics")
    inspect_parser.add_argument("--mcnp-version", default=None, dest="mcnp_version")

    plan_parser = subparsers.add_parser("plan-workflow")
    plan_parser.add_argument("--input", default=None, dest="input")
    plan_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    plan_parser.add_argument("--workflow-mode", required=True, dest="workflow_mode")
    plan_parser.add_argument("--source-strategy", default=None, dest="source_strategy")
    plan_parser.add_argument("--postprocess", default="none", dest="postprocess")
    plan_parser.add_argument("--nps", default=None, dest="nps")

    patch_parser = subparsers.add_parser("patch-deck")
    patch_parser.add_argument("--input", default=None, dest="input")
    patch_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    patch_parser.add_argument("--output", required=True, dest="output")
    patch_parser.add_argument("--nps", default=None, dest="nps")
    patch_parser.add_argument("--source-strategy", default="preserve_existing_source", dest="source_strategy")
    patch_parser.add_argument("--source-position", nargs=3, type=float, default=None, dest="source_position")
    patch_parser.add_argument("--source-energy", type=float, default=None, dest="source_energy")
    patch_parser.add_argument("--source-particle", default=None, dest="source_particle")
    patch_parser.add_argument("--source-radius", type=float, default=None, dest="source_radius")
    patch_parser.add_argument("--source-ext", type=float, default=0, dest="source_ext")
    patch_parser.add_argument("--source-card-id", type=int, default=None, dest="source_card_id")

    prep_parser = subparsers.add_parser("prepare-workflow")
    prep_parser.add_argument("--input", default=None, dest="input")
    prep_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    prep_parser.add_argument("--work-dir", required=True, dest="work_dir")
    prep_parser.add_argument("--workflow-mode", required=True, dest="workflow_mode")
    prep_parser.add_argument("--source-strategy", default=None, dest="source_strategy")
    prep_parser.add_argument("--postprocess", default="none", dest="postprocess")
    prep_parser.add_argument("--nps", default=None, dest="nps")
    prep_parser.add_argument("--source-position", nargs=3, type=float, default=None, dest="source_position")
    prep_parser.add_argument("--source-energy", type=float, default=None, dest="source_energy")
    prep_parser.add_argument("--source-particle", default=None, dest="source_particle")
    prep_parser.add_argument("--source-radius", type=float, default=None, dest="source_radius")
    prep_parser.add_argument("--source-ext", type=float, default=0, dest="source_ext")
    prep_parser.add_argument("--source-card-id", type=int, default=None, dest="source_card_id")
    prep_parser.add_argument("--diagnostics", action="store_true", default=False, dest="diagnostics")
    prep_parser.add_argument("--mcnp-version", default=None, dest="mcnp_version")

    rdsw_parser = subparsers.add_parser("run-disk-sweep")
    rdsw_parser.add_argument("--input", default=None, dest="input")
    rdsw_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    rdsw_parser.add_argument("--work-dir", required=True, dest="work_dir")
    rdsw_parser.add_argument("--distances", nargs="*", type=float, default=None, dest="distances")
    rdsw_parser.add_argument("--start", type=float, default=None, dest="start")
    rdsw_parser.add_argument("--stop", type=float, default=None, dest="stop")
    rdsw_parser.add_argument("--step", type=float, default=None, dest="step")
    rdsw_parser.add_argument("--axis", default="z", dest="axis")
    rdsw_parser.add_argument("--reference-position", nargs=3, type=float, default=None, dest="reference_position")
    rdsw_parser.add_argument("--reference-point", default=None, dest="reference_point")
    rdsw_parser.add_argument("--direction", type=float, default=1, dest="direction")
    rdsw_parser.add_argument("--source-energy", type=float, required=True, dest="source_energy")
    rdsw_parser.add_argument("--source-radius", type=float, required=True, dest="source_radius")
    rdsw_parser.add_argument("--source-particle", default=None, dest="source_particle")
    rdsw_parser.add_argument("--source-ext", type=float, default=0, dest="source_ext")
    rdsw_parser.add_argument("--source-card-id", type=int, default=None, dest="source_card_id")
    rdsw_parser.add_argument("--nps", default=None, dest="nps")
    rdsw_parser.add_argument("--postprocess", default="none", dest="postprocess")
    rdsw_parser.add_argument("--mpi-config", default=None, dest="mpi_config")
    rdsw_parser.add_argument("--mcnp-outputs", nargs="*", default=None, dest="mcnp_outputs")
    rdsw_parser.add_argument("--csv-dir", default=None, dest="csv_dir")
    rdsw_parser.add_argument("--plot-dir", default=None, dest="plot_dir")
    rdsw_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    rdsw_parser.add_argument("--execute", action="store_false", dest="dry_run")
    rdsw_parser.add_argument("--confirm-mpi", action="store_true", default=False)

    dsw_parser = subparsers.add_parser("prepare-disk-sweep")
    dsw_parser.add_argument("--input", default=None, dest="input")
    dsw_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    dsw_parser.add_argument("--work-dir", required=True, dest="work_dir")
    dsw_parser.add_argument("--distances", nargs="*", type=float, default=None, dest="distances")
    dsw_parser.add_argument("--start", type=float, default=None, dest="start")
    dsw_parser.add_argument("--stop", type=float, default=None, dest="stop")
    dsw_parser.add_argument("--step", type=float, default=None, dest="step")
    dsw_parser.add_argument("--axis", default="z", dest="axis")
    dsw_parser.add_argument("--reference-position", nargs=3, type=float, default=None, dest="reference_position")
    dsw_parser.add_argument("--reference-point", default=None, dest="reference_point")
    dsw_parser.add_argument("--direction", type=float, default=1, dest="direction")
    dsw_parser.add_argument("--source-energy", type=float, required=True, dest="source_energy")
    dsw_parser.add_argument("--source-radius", type=float, required=True, dest="source_radius")
    dsw_parser.add_argument("--source-particle", default=None, dest="source_particle")
    dsw_parser.add_argument("--source-ext", type=float, default=0, dest="source_ext")
    dsw_parser.add_argument("--source-card-id", type=int, default=None, dest="source_card_id")
    dsw_parser.add_argument("--nps", default=None, dest="nps")
    dsw_parser.add_argument("--postprocess", default="none", dest="postprocess")

    sweep_parser = subparsers.add_parser("prepare-point-sweep")
    sweep_parser.add_argument("--input", default=None, dest="input")
    sweep_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    sweep_parser.add_argument("--work-dir", required=True, dest="work_dir")
    sweep_parser.add_argument("--distances", nargs="*", type=float, default=None, dest="distances")
    sweep_parser.add_argument("--start", type=float, default=None, dest="start")
    sweep_parser.add_argument("--stop", type=float, default=None, dest="stop")
    sweep_parser.add_argument("--step", type=float, default=None, dest="step")
    sweep_parser.add_argument("--axis", default="z", dest="axis")
    sweep_parser.add_argument("--reference-position", nargs=3, type=float, default=None, dest="reference_position")
    sweep_parser.add_argument("--reference-point", default=None, dest="reference_point")
    sweep_parser.add_argument("--direction", type=float, default=1, dest="direction")
    sweep_parser.add_argument("--source-energy", type=float, required=True, dest="source_energy")
    sweep_parser.add_argument("--source-particle", default=None, dest="source_particle")
    sweep_parser.add_argument("--nps", default=None, dest="nps")
    sweep_parser.add_argument("--postprocess", default="none", dest="postprocess")

    runs_parser = subparsers.add_parser("run-point-sweep")
    runs_parser.add_argument("--input", default=None, dest="input")
    runs_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    runs_parser.add_argument("--work-dir", required=True, dest="work_dir")
    runs_parser.add_argument("--distances", nargs="*", type=float, default=None, dest="distances")
    runs_parser.add_argument("--start", type=float, default=None, dest="start")
    runs_parser.add_argument("--stop", type=float, default=None, dest="stop")
    runs_parser.add_argument("--step", type=float, default=None, dest="step")
    runs_parser.add_argument("--axis", default="z", dest="axis")
    runs_parser.add_argument("--reference-position", nargs=3, type=float, default=None, dest="reference_position")
    runs_parser.add_argument("--reference-point", default=None, dest="reference_point")
    runs_parser.add_argument("--direction", type=float, default=1, dest="direction")
    runs_parser.add_argument("--source-energy", type=float, required=True, dest="source_energy")
    runs_parser.add_argument("--source-particle", default=None, dest="source_particle")
    runs_parser.add_argument("--nps", default=None, dest="nps")
    runs_parser.add_argument("--postprocess", default="none", dest="postprocess")
    runs_parser.add_argument("--mpi-config", default=None, dest="mpi_config")
    runs_parser.add_argument("--mcnp-outputs", nargs="*", default=None, dest="mcnp_outputs")
    runs_parser.add_argument("--csv-dir", default=None, dest="csv_dir")
    runs_parser.add_argument("--plot-dir", default=None, dest="plot_dir")
    runs_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    runs_parser.add_argument("--execute", action="store_false", dest="dry_run")
    runs_parser.add_argument("--confirm-mpi", action="store_true", default=False)

    runwf_parser = subparsers.add_parser("run-workflow")
    runwf_parser.add_argument("--input", default=None, dest="input")
    runwf_parser.add_argument("--builtin-model", default=None, dest="builtin_model")
    runwf_parser.add_argument("--work-dir", required=True, dest="work_dir")
    runwf_parser.add_argument("--workflow-mode", required=True, dest="workflow_mode")
    runwf_parser.add_argument("--source-strategy", default=None, dest="source_strategy")
    runwf_parser.add_argument("--postprocess", default="none", dest="postprocess")
    runwf_parser.add_argument("--nps", default=None, dest="nps")
    runwf_parser.add_argument("--mpi-config", default=None, dest="mpi_config")
    runwf_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    runwf_parser.add_argument("--execute", action="store_false", dest="dry_run")
    runwf_parser.add_argument("--confirm-mpi", action="store_true", default=False)
    runwf_parser.add_argument("--mcnp-output", default=None, dest="mcnp_output")
    runwf_parser.add_argument("--csv-output", default=None, dest="csv_output")
    runwf_parser.add_argument("--plot-output", default=None, dest="plot_output")
    runwf_parser.add_argument("--source-position", nargs=3, type=float, default=None, dest="source_position")
    runwf_parser.add_argument("--source-energy", type=float, default=None, dest="source_energy")
    runwf_parser.add_argument("--source-particle", default=None, dest="source_particle")
    runwf_parser.add_argument("--source-radius", type=float, default=None, dest="source_radius")
    runwf_parser.add_argument("--source-ext", type=float, default=0, dest="source_ext")
    runwf_parser.add_argument("--source-card-id", type=int, default=None, dest="source_card_id")

    batchwf_parser = subparsers.add_parser("batch-workflow")
    batchwf_parser.add_argument("--input-dir", required=True, dest="input_dir")
    batchwf_parser.add_argument("--work-dir", required=True, dest="work_dir")
    batchwf_parser.add_argument("--workflow-mode", required=True, dest="workflow_mode")
    batchwf_parser.add_argument("--source-strategy", default=None, dest="source_strategy")
    batchwf_parser.add_argument("--postprocess", default="none", dest="postprocess")
    batchwf_parser.add_argument("--nps", default=None, dest="nps")
    batchwf_parser.add_argument("--input-files", nargs="*", default=None, dest="input_files")
    batchwf_parser.add_argument("--mpi-config", default=None, dest="mpi_config")
    batchwf_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    batchwf_parser.add_argument("--execute", action="store_false", dest="dry_run")
    batchwf_parser.add_argument("--confirm-mpi", action="store_true", default=False)
    batchwf_parser.add_argument("--mcnp-outputs", nargs="*", default=None, dest="mcnp_outputs")
    batchwf_parser.add_argument("--csv-dir", default=None, dest="csv_dir")
    batchwf_parser.add_argument("--plot-dir", default=None, dest="plot_dir")

    pp_parser = subparsers.add_parser("postprocess-workflow")
    pp_parser.add_argument("--input", required=True, dest="input")
    pp_parser.add_argument("--work-dir", required=True, dest="work_dir")
    pp_parser.add_argument("--mode", default="csv", dest="mode")
    pp_parser.add_argument("--mcnp-output", default=None, dest="mcnp_output")
    pp_parser.add_argument("--csv-output", default=None, dest="csv_output")
    pp_parser.add_argument("--plot-output", default=None, dest="plot_output")

    spe_parser = subparsers.add_parser("fit-geb-from-spe")
    spe_parser.add_argument("--spe", action="append", required=True, dest="spe_files")
    spe_parser.add_argument("--profile-path", default=None)
    spe_parser.add_argument("--profile-name", default=None)

    origin_parser = subparsers.add_parser("origin-export")
    origin_parser.add_argument("--target-dir", required=True)
    origin_parser.add_argument("--csv-pattern", default="*_Data.csv")
    origin_parser.add_argument("--temp-workspace", default="C:/MCNP_Tmp")
    origin_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    origin_parser.add_argument("--execute", action="store_false", dest="dry_run")
    origin_parser.add_argument("--confirm-origin", action="store_true", default=False)

    batch_parser = subparsers.add_parser("batch-run")
    batch_parser.add_argument("--base-file", required=True)
    batch_parser.add_argument("--output-dir", required=True)
    batch_parser.add_argument("--reference-point", required=True)
    batch_parser.add_argument("--nps", required=True)
    batch_parser.add_argument("--distance-start", required=True, type=float)
    batch_parser.add_argument("--distance-end", required=True, type=float)
    batch_parser.add_argument("--distance-step", required=True, type=float)
    batch_parser.add_argument("--custom-energy-kev", required=True, type=float)
    batch_parser.add_argument("--geb", nargs=3, type=float)
    batch_parser.add_argument("--mpi-command", required=True)
    batch_parser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
    batch_parser.add_argument("--execute", action="store_false", dest="dry_run")
    batch_parser.add_argument("--confirm-mpi", action="store_true", default=False)
    batch_parser.add_argument("--profile-path", default=None)
    batch_parser.add_argument("--profile-name", default=None)

    validate_parser = subparsers.add_parser("validate-run")
    validate_parser.add_argument("--run-dir")
    validate_parser.add_argument("--manifest")

    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_command(args)
    except Exception as exc:  # noqa: BLE001 - CLI must emit JSON on failure.
        return {"ok": False, "warnings": [], "errors": [str(exc)]}


def entrypoint(argv: list[str] | None = None) -> int:
    """Console-script entry point that emits ASCII-safe JSON."""
    payload = main(argv)
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2))
    sys.stdout.write("\n")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
