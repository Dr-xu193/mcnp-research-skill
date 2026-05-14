# MCNP Workflow CLI

## Capability Matrix

| Command | Purpose | Runs MCNP? |
|---------|---------|------------|
| `inspect-deck` | Detect cards (NPS, MODE, SDEF, F tallies, GEB) in a single deck | No |
| `plan-workflow` | Produce a structured plan from inspection + user intent | No |
| `patch-deck` | Apply NPS / point_sdef_pos / disk_tr1 patches to a single deck | No |
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

### 7. Disk source via TRn transform

```powershell
python -m mcnp_research_skill.cli patch-deck `
  --input A.txt `
  --output A_disk.txt `
  --source-strategy disk_tr1 `
  --source-position 0 0 10 `
  --source-radius 0.15 `
  --source-energy 0.662 `
  --source-ext 0 `
  --nps 1e7
```

**disk_tr1 parameters:**

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `--source-position X Y Z` | Yes | TRn translation position (3 numbers) |
| `--source-energy ENERGY` | Yes | Source energy in MeV (must be positive) |
| `--source-radius RADIUS` | Yes | Disk radius (must be positive) |
| `--source-ext EXT` | No (default 0) | SDEF ext parameter |
| `--source-card-id N` | No (auto) | Explicit TR/SI/SP card ID; auto-selected to avoid conflicts if omitted |
| `--source-particle` | No (default photon/2) | Only `p`/`photon`/`2` currently supported |

Generated cards (example with auto card-id=2):
```
tr2 0 0 10
sdef pos=0 0 0 rad=d2 ext=0 par=2 tr=2 erg=0.662
si2 0 0.15
sp2 -21 1
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
| `MISSING_SOURCE_RADIUS` | `disk_tr1` requires `--source-radius` |
| `INVALID_SOURCE_RADIUS` | source_radius must be a positive number |
| `INVALID_SOURCE_EXT` | source_ext must be numeric |
| `INVALID_SOURCE_CARD_ID` | source_card_id must be a positive integer |
| `SOURCE_CARD_ID_CONFLICT` | source_card_id is already used by existing TR/SI/SP |
| `MISSING_SOURCE_POSITION` | source_position is required |
| `INVALID_SOURCE_POSITION` | source_position must be exactly 3 numbers |
| `UNSUPPORTED_SOURCE_STRATEGY` | source_strategy not in preserve_existing_source / point_sdef_pos / disk_tr1 |
| `POSTPROCESS_ALL_FAILED` | Postprocess failed for every swept distance |
| `SWEEP_ALL_FAILED` | Every distance point failed to prepare |
| `PREPARE_FAILED` | A single prepare step returned an error |
