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
from .workflow.planner import plan_workflow
from .workflow.prepare import prepare_workflow
from .mcnp_input.generator import generate_mcnp_inputs
from .mcnp_output.tally_extractor import extract_tally_csvs
from .mcnp_run.mpi_runner import run_mpi_batch
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


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    """Execute a parsed CLI command and return a structured result."""
    if args.command == "init":
        return write_default_profiles(
            path=args.profile_path,
            force=bool(args.force),
            active_profile=str(args.profile_name),
        )

    if args.command == "inspect-deck":
        return inspect_deck_file(args.input)

    if args.command == "plan-workflow":
        inspection = inspect_deck_file(args.input)
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
        result = patch_deck_file(
            args.input, args.output,
            nps=getattr(args, "nps", None),
            source_strategy=getattr(args, "source_strategy", "preserve_existing_source"),
        )
        result.pop("text", None)
        return result

    if args.command == "prepare-workflow":
        return prepare_workflow(
            input_path=args.input,
            work_dir=args.work_dir,
            workflow_mode=args.workflow_mode,
            source_strategy=getattr(args, "source_strategy", None),
            postprocess=getattr(args, "postprocess", "none"),
            nps=getattr(args, "nps", None),
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

    for command in ["run-mpi", "extract-csv", "plot-spectra"]:
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", required=True)
        subparser.add_argument("--dry-run", action="store_true", dest="dry_run", default=True)
        subparser.add_argument("--execute", action="store_false", dest="dry_run")
        if command in {"run-mpi"}:
            subparser.add_argument("--confirm-mpi", action="store_true", default=False)

    inspect_parser = subparsers.add_parser("inspect-deck")
    inspect_parser.add_argument("--input", required=True, dest="input")

    plan_parser = subparsers.add_parser("plan-workflow")
    plan_parser.add_argument("--input", required=True, dest="input")
    plan_parser.add_argument("--workflow-mode", required=True, dest="workflow_mode")
    plan_parser.add_argument("--source-strategy", default=None, dest="source_strategy")
    plan_parser.add_argument("--postprocess", default="none", dest="postprocess")
    plan_parser.add_argument("--nps", default=None, dest="nps")

    patch_parser = subparsers.add_parser("patch-deck")
    patch_parser.add_argument("--input", required=True, dest="input")
    patch_parser.add_argument("--output", required=True, dest="output")
    patch_parser.add_argument("--nps", default=None, dest="nps")
    patch_parser.add_argument("--source-strategy", default="preserve_existing_source", dest="source_strategy")

    prep_parser = subparsers.add_parser("prepare-workflow")
    prep_parser.add_argument("--input", required=True, dest="input")
    prep_parser.add_argument("--work-dir", required=True, dest="work_dir")
    prep_parser.add_argument("--workflow-mode", required=True, dest="workflow_mode")
    prep_parser.add_argument("--source-strategy", default=None, dest="source_strategy")
    prep_parser.add_argument("--postprocess", default="none", dest="postprocess")
    prep_parser.add_argument("--nps", default=None, dest="nps")

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
