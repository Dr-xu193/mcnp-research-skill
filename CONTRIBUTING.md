# Contributing

## Quick Start

```powershell
git clone https://github.com/Dr-xu193/mcnp-research-skill.git
cd mcnp-research-skill
python -m pip install -e .
python -m pytest -q
```

## Project Structure

```
mcnp_research_skill/
├── cli.py                 # 26 CLI subcommands
├── models/                # Built-in model registry + fixtures
├── mcnp_input/            # Inspection, patching, diagnostics, generation
├── mcnp_output/           # Tally CSV extraction, failure analysis
├── mcnp_run/              # MPI runner, runtime preflight
├── workflow/              # Planner, prepare, run, batch, sweep, postprocess
│   ├── nl_planner.py      # Natural-language request parser
│   ├── execute_plan.py    # Confirmation-safe plan executor
│   └── user_output.py     # Chinese user-facing response renderer
├── geb/                   # GEB fitting, peak detection, efficiency
├── spectra/               # Plotting
├── config/                # Profile system
└── origin/                # Origin export
```

## Running Tests

```powershell
# Full suite (no real MCNP/MPI execution)
python -m pytest -q

# Specific module
python -m pytest tests/workflow/test_nl_planner.py -v

# Single test
python -m pytest tests/workflow/test_nl_planner.py::test_plan_2x2_aluminum_shell -v
```

Tests **never** call real MCNP, mpirun, Origin, or win32com.  All MPI/runtime tests use `mock`.

## Commit Style

Follow the existing convention:

```
<type>(<scope>): <short description>
```

Types: `feat`, `fix`, `test`, `docs`, `chore`, `ci`

Examples:
- `feat(workflow): add natural-language planner`
- `fix(diagnostics): harden MCNP5 legacy text encoding checks`
- `test(workflow): add user scenario acceptance`

## Pull Request Checklist

- [ ] `python -m pytest -q` passes
- [ ] No real MCNP/MPI execution in tests
- [ ] New features have tests
- [ ] User-facing commands output Chinese text by default
- [ ] `--json` flag is available for automation
- [ ] Don't add unverified NaI models without explicit `verified=false`
- [ ] Don't auto-modify geometry/F card/material/source physics

## Design Boundaries (do not break)

- **Safety gates**: dry-run by default; execution requires `--execute --confirm-user`
- **F8 only**: CSV/plot postprocess only supports F8 pulse-height tally
- **No MCNP download/piracy**: never provide MCNP download links or license workarounds
- **No activity normalization**: Bq ≠ NPS; activity-to-count-rate not supported
- **Deterministic planner**: NL planner is rule-based, not an LLM
- **Reference points**: never assume detector front surface unless explicitly verified from fixture
- **Legacy isolation**: do not modify `legacy/gui.py`, `origin_exporter.py`, `input generator.py` physics logic

## Branch Strategy

```
main                  ← stable releases (v0.3.0)
feature/profiles-init ← active development
legacy-v0.1           ← old main backup (read-only)
```

## Questions?

Open an issue on GitHub.
