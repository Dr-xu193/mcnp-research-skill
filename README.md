# MCNP Research Skill

`mcnp_research_skill` is a refactored MCNP5 research toolkit split from
`legacy/auto.py`. It keeps the migrated physics logic isolated in testable
Python modules and exposes ASCII-safe JSON CLI commands.

## Scope

The toolkit currently supports:

- MCNP input generation with distance, reference point, NPS, energy, composite source, and FT8 GEB controls.
- MPI batch dry-run planning and confirmed execution.
- F8 tally extraction to `*_Data.csv`.
- Spectra plotting with linear/log comparison PNG output.
- GEB CSV analysis and SPE-based GEB fitting.
- Origin OPJ export planning and confirmed execution.
- v0.2 tooling for diagnostics, batch runs, run manifests, and run validation.

It does not rewrite `auto.py` or `legacy/auto.py`, does not reconnect the GUI,
does not add MCP, and does not put Origin into the default pipeline.

## Install

From the repository root:

```powershell
python -m pip install -e .
```

Optional Origin automation dependencies:

```powershell
python -m pip install -e ".[origin]"
```

After installation, use either:

```powershell
mcnp-research --help
python -m mcnp_research_skill.cli --help
```

## Safety Defaults

- Default mode is `dry_run`.
- Real MPI execution requires `--execute --confirm-mpi`.
- Real Origin export requires `--execute --confirm-origin`.
- Core modules must return structured dicts and must not use tkinter, messagebox, or print.
- Tests must not call MCNP, mpirun, Origin, or win32com.
- Local smoke input `D:/codex/agent/A.txt` is intentionally ignored by git.

## Core Commands

```powershell
mcnp-research doctor --config configs/example.pipeline.yaml
mcnp-research run-core-pipeline --config configs/example.pipeline.yaml --dry-run
mcnp-research fit-geb-from-spe --spe file1.spe --spe file2.spe
mcnp-research origin-export --target-dir D:/MCNP/work --dry-run
mcnp-research validate-run --run-dir D:/MCNP/work/run_663
```

## Batch Workflow

Example dry-run for a 663.52 keV study over 16.3 cm to 36.3 cm in 5 cm steps:

```powershell
mcnp-research batch-run --base-file D:/codex/agent/A.txt --output-dir D:/MCNP/work/run_663 `
  --reference-point crystal_center --nps 100000000 `
  --distance-start 16.3 --distance-end 36.3 --distance-step 5 `
  --custom-energy-kev 663.52 --geb 0.2 0.3 0.6 `
  --mpi-command "D:/MCNP/MPICH/mpd/bin/MPIRun.exe -np 1 D:/MCNP/MCNP5/MCNP5mpi.exe" --dry-run
```

Real execution uses the same command with:

```powershell
--execute --confirm-mpi
```

For local smoke tests, keep NPS at or below `1000000` unless a long production
run is explicitly intended.

## Reproducibility

`batch-run --execute --confirm-mpi` writes `manifest.json` into the batch run
directory. The manifest records the config, base file SHA256, git commit, tool
version, subrun outputs, warnings, and errors. Dry-run returns the same manifest
shape as `manifest_preview` without writing it.

Validate a finished run:

```powershell
mcnp-research validate-run --run-dir D:/MCNP/work/run_663
```

## Verification

```powershell
python -m compileall -q mcnp_research_skill tests
python -m pytest -q
```

See `docs/FINAL_CHECKLIST.md` for dry-run acceptance and real MPI/Origin
pre-run checklists.
