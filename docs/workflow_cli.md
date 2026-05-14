# MCNP Workflow CLI

## Capability Matrix

| Command | Purpose | Runs MCNP? |
|---------|---------|------------|
| `inspect-deck` | Detect cards (NPS, MODE, SDEF, F tallies, GEB) in a single deck | No |
| `plan-workflow` | Produce a structured plan from inspection + user intent | No |
| `patch-deck` | Apply NPS / point-sdef_pos patches to a single deck | No |
| `prepare-workflow` | Inspect → plan → patch/copy → write manifest | No |
| `run-workflow` | Prepare → optionally run MCNP → optionally F8 postprocess | **Yes (if --execute)** |
| `batch-workflow` | Batch prepare/run for all *.txt decks in a directory | **Yes (if --execute)** |
| `postprocess-workflow` | Extract F8 CSV / plot from an existing MCNP output file | No |
| `prepare-point-sweep` | Generate point-source distance sweep decks | No |
| `run-point-sweep` | Sweep → optionally run MCNP → optionally F8 postprocess | **Yes (if --execute)** |

## Current Boundaries

- **run-only** does not require an F8 tally card.
- **CSV extraction / plotting** currently supports **only F8** pulse-height tallies.
- F4, F5, F6, and FMESH tallies are detected and reported but **not** supported for CSV/plot.
- Missing GEB (FT8 GEB) is **not** an error for CSV/plot.
- All commands default to **dry-run** — no MCNP is ever executed without `--execute --confirm-mpi`.
- Real execution requires **both** `--execute --confirm-mpi` and an `--mpi-config` (a YAML file with `mpi_command`).
- The point-source sweep (`point_sdef_pos`) is the only source strategy currently implemented for sweeping.
- Reference positions, axes, and directions are pure mathematical transforms; no NaI geometry or crystal-front-surface assumptions are baked in.
- Do **not** hand-edit MCNP decks — use the CLI `patch-deck`, `prepare-workflow`, or `run-workflow` commands.

---

## Typical Command Examples

### 1. Inspect a deck

```powershell
python -m mcnp_research_skill.cli inspect-deck --input A.txt
```

### 2. Batch-run existing decks (no postprocess)

```powershell
python -m mcnp_research_skill.cli batch-workflow `
  --input-dir decks `
  --work-dir runs/batch_001 `
  --workflow-mode run-only `
  --postprocess none
```

### 3. Preserve source, only patch NPS (dry-run)

```powershell
python -m mcnp_research_skill.cli batch-workflow `
  --input-dir decks `
  --work-dir runs/batch_nps `
  --workflow-mode patch-and-run `
  --source-strategy preserve_existing_source `
  --postprocess none `
  --nps 1e7
```

### 4. Point-source distance sweep 10–25 cm, step 5 (prepare only)

```powershell
python -m mcnp_research_skill.cli prepare-point-sweep `
  --input A.txt `
  --work-dir runs/point_sweep `
  --start 10 --stop 25 --step 5 `
  --axis z `
  --reference-position 0 0 0 `
  --direction 1 `
  --source-energy 0.662 `
  --nps 1e7
```

### 5. Point-source sweep + dry-run

```powershell
python -m mcnp_research_skill.cli run-point-sweep `
  --input A.txt `
  --work-dir runs/point_sweep_run `
  --start 10 --stop 25 --step 5 `
  --axis z `
  --reference-position 0 0 0 `
  --direction 1 `
  --source-energy 0.662 `
  --nps 1e7 `
  --postprocess none
```

### 6. Point-source sweep → real MCNP execution → F8 CSV + plot

> **WARNING:** This command actually executes MCNP.  Only run it after
> reviewing the dry-run plan and confirming you want MPI execution.

```powershell
python -m mcnp_research_skill.cli run-point-sweep `
  --input A.txt `
  --work-dir runs/point_sweep_run `
  --start 10 --stop 25 --step 5 `
  --axis z `
  --reference-position 0 0 0 `
  --direction 1 `
  --source-energy 0.662 `
  --nps 1e7 `
  --postprocess csv-and-plot `
  --mpi-config cfg.yaml `
  --execute `
  --confirm-mpi
```

---

## Common Error Codes

| Code | Meaning |
|------|---------|
| `CSV_REQUIRES_F8` | Postprocess requested but deck has no F8 tally |
| `NO_SUPPORTED_TALLY_FOR_CSV` | No tally card at all in deck |
| `MULTIPLE_NPS` | More than one NPS card detected |
| `MISSING_CONFIRM_MPI` | `--execute` passed without `--confirm-mpi` |
| `MISSING_MPI_CONFIG` | `--execute` passed without `--mpi-config` |
| `MISSING_SOURCE_ENERGY` | `point_sdef_pos` requires `--source-energy` |
| `INVALID_SWEEP_RANGE` | Sweep start > stop, step <= 0, or no distances given |
| `INVALID_SWEEP_AXIS` | Sweep axis not one of x/y/z |
| `INVALID_REFERENCE_POSITION` | Reference position is not exactly 3 numbers |
| `INPUT_FILE_NOT_FOUND` | Input file or directory does not exist |
| `RUNNER_FAILED` | MPI runner raised an exception |
| `POSTPROCESS_ALL_FAILED` | Postprocess failed for every swept distance |
| `SWEEP_ALL_FAILED` | Every distance point failed to prepare |
| `PREPARE_FAILED` | A single prepare step returned an error |
