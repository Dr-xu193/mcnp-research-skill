"""Command-line interface for spectrum plotting."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .plotter import plot_spectra


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the spectra CLI and return a structured result."""
    parser = argparse.ArgumentParser(prog="python -m mcnp_research_skill.spectra.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plot_parser = subparsers.add_parser("plot", help="plot one or more spectrum CSV files")
    plot_parser.add_argument("--csv", action="append", required=True, dest="csv_files")
    plot_parser.add_argument("--output", required=True, dest="output_path")
    plot_parser.add_argument("--mode", default="merged", choices=["merged"])
    plot_parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    args = parser.parse_args(argv)

    if args.command == "plot":
        return plot_spectra(
            csv_files=args.csv_files,
            output_path=args.output_path,
            mode=args.mode,
            dry_run=args.dry_run,
        )

    return {"ok": False, "error": f"Unsupported command: {args.command}"}


if __name__ == "__main__":
    cli_result = main()
    sys.stdout.write(json.dumps(cli_result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    raise SystemExit(0 if cli_result.get("ok") else 1)
