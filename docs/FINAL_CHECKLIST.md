# Final Acceptance Checklist

## Completed Modules

- `mcnp_research_skill.spectra`: CSV spectrum loading and linear/log plotting.
- `mcnp_research_skill.mcnp_input`: MCNP input generation with NPS, TR1, source cards, composite sources, and FT8 GEB handling.
- `mcnp_research_skill.mcnp_run`: MPI dry-run planning and confirmed execution guard.
- `mcnp_research_skill.mcnp_output`: F8 tally extraction to `*_Data.csv`.
- `mcnp_research_skill.pipeline`: core single-run orchestration.
- `mcnp_research_skill.batch`: distance-expanded batch orchestration.
- `mcnp_research_skill.diagnostics`: read-only doctor checks.
- `mcnp_research_skill.manifest`: run manifest creation and validation.
- `mcnp_research_skill.geb`: CSV GEB analysis and SPE-based GEB fitting.
- `mcnp_research_skill.origin`: Origin OPJ dry-run/export isolation.
- `mcnp_research_skill.cli`: ASCII-safe JSON CLI and installable console script.

## Not Done By Design

- MCP is not implemented.
- GUI is not reconnected.
- Origin is not part of the default pipeline.
- Natural language parsing is not in the core library.
- `auto.py` and `legacy/auto.py` remain read-only migration baselines.

## Final Test Commands

```powershell
python -m compileall -q mcnp_research_skill tests
python -m pytest -q
```

## Dry-run Acceptance

1. Run diagnostics:

```powershell
python -m mcnp_research_skill.cli doctor --config configs/example.pipeline.yaml
```

2. Run a single pipeline dry-run:

```powershell
python -m mcnp_research_skill.cli run-core-pipeline --config configs/example.pipeline.yaml --dry-run
```

3. Run a batch dry-run:

```powershell
python -m mcnp_research_skill.cli batch-run --base-file D:/codex/agent/A.txt --output-dir D:/MCNP/work/run_663 --reference-point crystal_center --nps 1000000 --distance-start 16.3 --distance-end 36.3 --distance-step 5 --custom-energy-kev 663.52 --geb 0.2 0.3 0.6 --mpi-command "mpirun -np 1 mcnp5mpi.exe" --dry-run
```

4. Confirm JSON output contains planned files, planned MPI commands, planned CSV files, planned plots, and `manifest_preview`.
5. Confirm dry-run did not create numeric input files, `i.txt`, `o.txt`, CSV files, PNG files, or `manifest.json`.

## Real MPI Pre-run Checklist

- Confirm the base deck is correct and contains `f8:p,e`.
- Confirm distance range, reference point, NPS, energy, and GEB parameters.
- Run `doctor` and resolve errors.
- Run `batch-run --dry-run` and inspect planned subdirectories, commands, and output names.
- Confirm `mpi_command` points to the intended MCNP5 MPI executable.
- Confirm the run directory is not a legacy or source directory.
- Confirm the user accepts creation of run artifacts and cleanup of module-owned temporary files.
- Use real execution only with:

```powershell
python -m mcnp_research_skill.cli batch-run ... --execute --confirm-mpi
```

## Real Origin Pre-run Checklist

- Run `origin-export --dry-run` first.
- Confirm `*_Data.csv` files are correct.
- Confirm Windows, Origin, and pywin32 are available.
- Save other Origin work before confirmed automation.
- Confirm `temp_workspace` does not contain user files that must be preserved.
- Use real execution only with:

```powershell
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --execute --confirm-origin
```

## Share With Another User

1. Push the repository and tags.
2. Ask the user to install with `python -m pip install -e .`.
3. Ask the user to run `python -m pytest -q`.
4. Start with `doctor` and dry-run commands.
5. Use `validate-run` after confirmed production runs.
6. Keep `auto.py`, `legacy/auto.py`, and local smoke inputs unmodified.
