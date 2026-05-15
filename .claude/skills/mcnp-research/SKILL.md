# MCNP Research Skill

MCNP5 nuclear detector simulation toolkit with natural-language workflow
planning, built-in detector models, input diagnostics, and postprocessing.

## When to use

- User wants to simulate a NaI(Tl) detector with MCNP5
- User needs distance sweeps (point source or disk source)
- User needs MCNP5_RSICC 1.14 input format checking
- User needs F8 pulse-height tally CSV extraction or plotting
- User wants to analyze MCNP failure output logs

## CLI entry point

```powershell
python -m mcnp_research_skill.cli <command> [--json]
```

Default output is **Chinese user-facing text**.  Use `--json` for structured
JSON that can be parsed programmatically.

## Commands

### Natural-language workflow

| Command | Purpose |
|---------|---------|
| `plan-request --text "..."` | Parse Chinese/English request into structured plan |
| `execute-plan --plan-file plan.json` | Execute plan (dry-run default, `--execute --confirm-user` for real) |
| `runtime-check` | Check MCNP/MPI environment readiness |

### Deck inspection / repair

| Command | Purpose |
|---------|---------|
| `diagnose-deck --input A.txt` | MCNP5_RSICC 1.14 compatibility diagnostics |
| `repair-deck --input A.txt --output B.txt` | Safe format repair (tabs, continuation, Unicode) |
| `inspect-deck --input A.txt` | Detect NPS, MODE, SDEF, F tallies, GEB |

### Model management

| Command | Purpose |
|---------|---------|
| `models list` | List built-in detector models |
| `models inspect <id>` | Inspect a built-in model |

### Patch / prepare / run

| Command | Purpose |
|---------|---------|
| `patch-deck` | Apply NPS / source strategy to a deck |
| `prepare-workflow` | Full prepare pipeline (inspect → plan → patch → manifest) |
| `run-workflow` | Prepare → run MCNP → F8 postprocess |

### Sweeps

| Command | Purpose |
|---------|---------|
| `prepare-point-sweep` | Generate point-source distance sweep decks |
| `run-point-sweep` | Sweep → run MCNP → postprocess |
| `prepare-disk-sweep` | Generate disk-source distance sweep decks |
| `run-disk-sweep` | Sweep → run MCNP → postprocess |

Sweep commands support `--builtin-model <id>` and `--reference-point <name>`.

### Postprocess / batch

| Command | Purpose |
|---------|---------|
| `postprocess-workflow` | F8 CSV + plot from existing MCNP output |
| `batch-workflow` | Batch prepare/run for `*.txt` decks in a directory |

### Failure analysis

| Command | Purpose |
|---------|---------|
| `analyze-run-failure --output o.txt` | Analyze MCNP output (first 300 lines) for failure diagnosis |

### Legacy (v0.1 compatibility)

| Command | Purpose |
|---------|---------|
| `batch-run` | Legacy batch pipeline |
| `generate-inputs` | Input generation from YAML config |
| `fit-geb-from-spe` | GEB fitting from SPE files |

## Built-in models

| ID | Description | Verified |
|----|-------------|----------|
| `nai_3x3_verified` | 3-inch NaI(Tl) from A.txt fixture | Yes |
| `nai_2x2_template` | 2-inch NaI(Tl) simplified template | No (user must validate) |
| `nai_1x1_template` | 1-inch NaI(Tl) simplified template | No (user must validate) |

## Reference points (per model)

| Canonical name | Chinese |
|---------------|---------|
| `nai_crystal_front_surface` | 碘化钠晶体前端表面 |
| `nai_crystal_center` | 碘化钠晶体中心 |
| `aluminum_shell_front` | 铝壳前表面 |

## Source strategies

| Strategy | Description |
|----------|-------------|
| `point_sdef_pos` | Point source (sweep default) |
| `disk_tr1` | Disk source via TRn transform |
| `preserve_existing_source` | Keep existing source, change NPS only |

## Safety rules

- **Dry-run by default**: never execute MCNP without `--execute --confirm-user`
- **No MCNP download/piracy**: MCNP requires RSICC license
- **F8 postprocess only**: CSV/plot only supports F8 pulse-height tally
- **F2/F4/F5/F6/FMESH**: run-only is allowed, CSV/plot is blocked
- **NPS ≠ Bq**: activity normalization is not supported

## Example workflow

```powershell
# 1. Parse user request
python -m mcnp_research_skill.cli --json plan-request \
  --text "3 inch NaI, Cs-137 point source, distance from crystal front 10 to 20 cm step 5 cm, nps 1e6, csv only" \
  --output plan.json

# 2. Show human_summary to user, get confirmation

# 3. Execute (dry-run)
python -m mcnp_research_skill.cli --json execute-plan --plan-file plan.json

# 4. If user confirms, real execution
python -m mcnp_research_skill.cli --json execute-plan --plan-file plan.json \
  --execute --confirm-user

# 5. If run fails, analyze
python -m mcnp_research_skill.cli --json analyze-run-failure \
  --output o.txt --context plan.json
```
