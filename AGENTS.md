# MCNP Research Skill Agent Guide

## Project Role

This project is an MCNP Research Skill toolkit split from `legacy/auto.py`.
It supports MCNP input generation, MPI dry-run/confirmed execution, F8 tally
CSV extraction, spectra plotting, GEB CSV analysis, SPE-based GEB fitting,
Origin OPJ dry-run/export planning, diagnostics, batch runs, manifests, and
run validation.

## Code Maintenance Rules

- Do not modify `auto.py` or `legacy/auto.py`.
- Do not change the physics algorithms without an explicit staged request.
- Do not put GUI logic into core modules.
- Core functions must return structured dicts with `ok`, `warnings`, and `errors`.
- External side effects must support `dry_run`.
- New behavior must have tests before implementation.
- CLI output must remain ASCII-safe JSON.
- Keep Origin out of the default pipeline.

## Safety Rules

- Default to `dry_run`.
- Real MPI execution requires `--execute --confirm-mpi`.
- Real Origin execution requires `--execute --confirm-origin`.
- Do not automatically delete user files.
- Do not overwrite legacy files.
- Do not call MCNP, mpirun, Origin, or win32com in tests.
- Do not use tkinter, messagebox, or print in core modules.
- Local smoke inputs such as `A.txt` must stay untracked.

## Common Commands

```powershell
python -m compileall -q mcnp_research_skill tests
python -m pytest -q
python -m mcnp_research_skill.cli doctor --config configs/example.pipeline.yaml
python -m mcnp_research_skill.cli run-core-pipeline --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli batch-run --base-file D:/codex/agent/A.txt --output-dir D:/MCNP/work/run_663 --reference-point crystal_center --nps 1000000 --distance-start 16.3 --distance-end 36.3 --distance-step 5 --custom-energy-kev 663.52 --geb 0.2 0.3 0.6 --mpi-command "mpirun -np 1 mcnp5mpi.exe" --dry-run
python -m mcnp_research_skill.cli validate-run --run-dir D:/MCNP/work/run_663
python -m mcnp_research_skill.cli fit-geb-from-spe --spe file1.spe --spe file2.spe
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --dry-run
```

## Current Boundaries

- MCP is not implemented.
- GUI is not reconnected.
- Natural language parsing is handled by the Agent, not by core Python modules.
- `legacy/auto.py` remains the read-only migration baseline.
