---
name: mcnp-research-pipeline
description: Use this skill for MCNP5 efficiency calibration workflows, including MCNP input generation, MPI batch dry-runs and confirmed execution, F8 tally CSV extraction, spectra plotting, GEB CSV analysis, SPE-based GEB fitting, and Origin OPJ dry-run/export planning.
---

# MCNP Research Pipeline

## When to use

Use this skill when working on MCNP5 detector efficiency calibration workflows in this repository, especially tasks involving input deck generation, MPI run planning, F8 tally CSV extraction, spectra comparison plots, GEB fitting from CSV or SPE data, and Origin OPJ export planning.

Do not use this skill for MCP server work, GUI rewrites, unrelated Python refactors, or changes to `auto.py` and `legacy/auto.py`.

## Available capabilities

- Generate MCNP input files from a base deck with source cards, NPS, distance/reference metadata, optional composite sources, and optional FT8 GEB cards.
- Plan or confirm MPI batch runs over numeric `.txt` input decks.
- Extract F8 tally output tables into UTF-8-SIG `*_Data.csv` files.
- Plot one or more spectra as linear/log comparison PNGs.
- Analyze CSV spectra for peak/FWHM/efficiency and fit GEB parameters.
- Fit GEB parameters from SPE files.
- Plan or confirm Origin OPJ exports from `*_Data.csv` files.

## Preferred workflow

1. inspect config
2. generate inputs with dry-run
3. run MPI with dry-run
4. only after user confirmation run MPI with --execute --confirm-mpi
5. extract CSV
6. plot spectra
7. run GEB CSV analysis if needed
8. fit GEB from SPE files if needed
9. Origin export only with dry-run first
10. real Origin export only with --execute --confirm-origin

## CLI commands

```powershell
python -m mcnp_research_skill.cli generate-inputs --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli run-mpi --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli extract-csv --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli plot-spectra --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli run-core-pipeline --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli fit-geb-from-spe --spe file1.spe --spe file2.spe
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --dry-run
```

Confirmed high-risk commands:

```powershell
python -m mcnp_research_skill.cli run-mpi --config configs/example.pipeline.yaml --execute --confirm-mpi
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --execute --confirm-origin
```

## Safety rules

- Keep default `dry_run` behavior unless the user explicitly requests real execution.
- Require `--execute --confirm-mpi` before any real MCNP/mpirun execution.
- Require `--execute --confirm-origin` before any real Origin COM automation.
- Keep CLI output as ASCII-safe JSON.
- Keep core functions returning structured dicts with `ok`, `warnings`, and `errors`.
- Run `python -m compileall -q mcnp_research_skill tests` and `python -m pytest -q` after changes.
- Preserve `auto.py` and `legacy/auto.py` exactly unless the user explicitly requests otherwise.

## High-risk operations

MPI execution can create, delete, and rename files in the MCNP working directory. Use dry-run first and inspect planned commands and output names.

Origin export can kill Origin processes, create temporary workspaces, copy files, call win32com, save `.opj` files, and clean temporary directories. Use dry-run first and require explicit confirmation before real execution.

## What not to do

- Do not modify `auto.py` or `legacy/auto.py`.
- Do not change the physical algorithms during documentation or orchestration work.
- Do not put tkinter, messagebox, print, or GUI state into core modules.
- Do not add Origin to the default pipeline.
- Do not call MCNP, mpirun, Origin, or win32com from tests.
- Do not silently ignore errors; return structured `errors` or `failed` entries.

## Expected outputs

Core functions should return dictionaries that include success state, dry-run state where relevant, generated or planned files, warnings, and errors. CLI commands should emit JSON to stdout and return a nonzero exit code when `ok` is false.

Generated artifacts are normally:

- Numeric MCNP input `.txt` files from input generation.
- Renamed MCNP output `.txt` files from confirmed MPI runs.
- `*_Data.csv` files from tally extraction.
- PNG spectra plots.
- GEB analysis dictionaries and report text.
- Planned or confirmed Origin `.opj` exports.

## Troubleshooting

- If a CLI command fails before running work, inspect the JSON `errors` field first.
- If config parsing fails, check `configs/example.pipeline.yaml` for required keys and scalar/list syntax.
- If MPI planning finds no files, confirm the work directory contains numeric `.txt` input decks such as `1.txt`.
- If plotting is skipped, confirm `*_Data.csv` files exist in the configured output directory.
- If SPE fitting returns `ok=false`, check whether at least three valid peak FWHM points were extracted.
- If Origin export fails, confirm it was run with dry-run first, then check whether pywin32 and Origin are available before using `--execute --confirm-origin`.
- If tests fail, run `python -m pytest -q` and fix the first concrete failure instead of changing physical logic.
