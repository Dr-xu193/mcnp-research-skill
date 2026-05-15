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
| `prepare-disk-sweep` | Generate disk_tr1 distance sweep decks | No |
| `run-disk-sweep` | Disk sweep → optionally run MCNP → optionally F8 postprocess | **Yes (if --execute)** |
| `run-point-sweep` | Sweep → optionally run MCNP → optionally F8 postprocess | **Yes (if --execute)** |
| `models list` | List registered built-in verified decks | No |
| `models inspect` | Inspect a built-in model (alias for inspect-deck) | No |

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

### 5. Disk-source sweep prepare only (no MCNP run)

```powershell
python -m mcnp_research_skill.cli prepare-disk-sweep `
  --input A.txt `
  --work-dir runs/disk_sweep `
  --start 10 --stop 25 --step 5 `
  --axis z `
  --reference-position 0 0 0 `
  --direction 1 `
  --source-energy 0.662 `
  --source-radius 0.15 `
  --nps 1e7
```

> prepare-disk-sweep generates disk_tr1 prepared decks at each distance.
> It does **not** run MCNP, extract CSV, or plot.  Reference positions,
> axes, and directions are pure mathematical transforms — no NaI
> geometry or crystal-front-surface assumptions are baked in.

### 5b. Disk-source sweep dry-run

```powershell
python -m mcnp_research_skill.cli run-disk-sweep `
  --input A.txt `
  --work-dir runs/disk_sweep_run `
  --start 10 --stop 25 --step 5 `
  --axis z `
  --reference-position 0 0 0 `
  --direction 1 `
  --source-energy 0.662 `
  --source-radius 0.15 `
  --nps 1e7 `
  --postprocess none
```

> Dry-run only — generates plans and runner_input_files but does **not**
> execute MCNP.  Real execution requires `--execute --confirm-mpi --mpi-config`.
>
> **CSV/plot still only supports F8.**  F4/F5/F6/FMESH tallies are detected
> but will return `CSV_REQUIRES_F8` if postprocess is requested.  Dry-run
> with `--postprocess csv` only marks `planned_not_executed` — no postprocess
> runs.  The MCNP output path priority for execute+postprocess is:
> 1. User-explicit `--mcnp-outputs`
> 2. Runner summary `completed[].output_path`
> 3. `MISSING_MCNP_OUTPUT` (error, not traceback)

### 5c. Disk-source sweep + real execution + F8 postprocess

> **WARNING:** This command actually executes MCNP.

```powershell
python -m mcnp_research_skill.cli run-disk-sweep `
  --input A.txt `
  --work-dir runs/disk_sweep_exec `
  --start 10 --stop 25 --step 5 `
  --axis z `
  --reference-position 0 0 0 `
  --direction 1 `
  --source-energy 0.662 `
  --source-radius 0.15 `
  --nps 1e7 `
  --postprocess csv-and-plot `
  --mpi-config cfg.yaml `
  --execute `
  --confirm-mpi
```

---

### 6. Point-source sweep + dry-run

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
| `MODEL_NOT_FOUND` | Built-in model id not found in registry |
| `MISSING_INPUT` | Neither `--input` nor `--builtin-model` was provided |
| `UNKNOWN_REFERENCE_POINT` | Named reference point not found in profile or built-in constants |

---

## Built-in Models (v0.2)

A minimal registry of verified MCNP decks shipped with the package.  Every
built-in model is a real, physically validated deck.  No unverified
detector sizes or geometries are included.

### Available models

| Model ID | Display Name | Verified | Status |
|----------|-------------|----------|--------|
| `nai_3x3_verified` | 3x3 NaI(Tl) verified deck | **yes** | verified |
| `nai_1x1_template` | 1x1 NaI(Tl) unverified template | **no** | template |
| `nai_2x2_template` | 2x2 NaI(Tl) unverified template | **no** | template |

**`nai_1x1_template` and `nai_2x2_template` are NOT verified models.**
They are simplified MCNP5-compatible starter decks.  Users MUST validate
all dimensions, materials, and settings against their own detector
datasheet before using for real analysis.

### Template design (1x1 / 2x2)

| Property | 1x1 Template | 2x2 Template |
|----------|-------------|-------------|
| Crystal diameter | 1 inch (2.54 cm) | 2 inch (5.08 cm) |
| Crystal radius | 1.27 cm | 2.54 cm |
| Crystal length | 1 inch (2.54 cm) | 2 inch (5.08 cm) |
| NaI(Tl) material | From A.txt fixture m1 | From A.txt fixture m1 |
| Al housing | From A.txt fixture m3 | From A.txt fixture m3 |
| Al wall thickness | 0.1 cm (assumed) | 0.1 cm (assumed) |
| Al window thickness | 0.1 cm (assumed) | 0.1 cm (assumed) |
| PMT / rear structure | None | None |
| GEB | None | None |
| Reference points | None verified | None verified |

**Assumptions** (both templates):
- Al housing wall 0.1 cm — user MUST validate
- Al front window 0.1 cm — user MUST validate
- No PMT, reflector, optical window, or rear structure
- z=0 is a template coordinate convention, not a measured physical surface
- Crystal dimensions from Saint-Gobain / vendor nominal datasheet conventions

**Basis**: NaI(Tl) composition and density from verified A.txt fixture.
Aluminum and air compositions from A.txt fixture.

**MCNP5 encoding**: All template decks use ASCII-only title and data cards.
Unicode punctuation (em dash, arrow) has been replaced with ASCII equivalents.

### Boundaries

- **Built-in models still go through the full deck-aware workflow**: inspect → plan → patch → prepare → run → postprocess.  No shortcuts, no fixed-NaI scripts.
- **Source strategy must still be explicit**: `preserve_existing_source`, `point_sdef_pos`, or `disk_tr1`.  There is no automatic source replacement for NaI models — no `encapsulated_disk_tr1`, no `custom_source_block`.
- **No detector front-surface reference point in the model registry**: the `nai_3x3_verified` entry does **not** define `reference_points`, `front_surface`, `detector_front`, or `crystal_front`.  Reference points come from the **profile** (`~/.mcnp-research/profiles.yaml`) or the **built-in constants** (`crystal_front_surface`, `crystal_center`, `aluminum_shell_surface`).  Requesting an unknown reference point returns a structured error with code `UNKNOWN_REFERENCE_POINT`.  Use `validate_reference_point()` from the registry module for boundary checks.
- **Explicit `--reference-position` always works**: sweep and prepare commands accept `--reference-position X Y Z` directly, no named reference point required.
- **No geometry deduction from model name**: the display name "3x3 NaI(Tl)" does not imply z=0, z=-0.34, z=7.62, or any other surface position.
- **Non-F8 tally rules unchanged**: run-only works regardless; csv/plot still requires F8.
- **Safety gates unchanged**: real MPI execution requires `--execute --confirm-mpi --mpi-config`.
- **MCNP5 compatibility**: the built-in fixture follows MCNP5 conventions — ≤80 columns, no tabs, valid continuation lines, no MCNP6-only syntax.

### CLI: list and inspect

```powershell
# List all built-in models
python -m mcnp_research_skill.cli models list

# Inspect a built-in model (runs inspect-deck internally)
python -m mcnp_research_skill.cli models inspect nai_3x3_verified
```

### CLI: prepare-workflow with built-in model (preserve_existing_source)

```powershell
python -m mcnp_research_skill.cli prepare-workflow `
  --builtin-model nai_3x3_verified `
  --work-dir runs/nai_preserve `
  --workflow-mode patch-and-run `
  --source-strategy preserve_existing_source `
  --nps 1e7 `
  --postprocess none
```

### CLI: prepare-workflow with built-in model (disk_tr1)

```powershell
python -m mcnp_research_skill.cli prepare-workflow `
  --builtin-model nai_3x3_verified `
  --work-dir runs/nai_disk_sweep `
  --workflow-mode patch-and-run `
  --source-strategy disk_tr1 `
  --source-position 0 0 15 `
  --source-radius 0.15 `
  --source-energy 0.662 `
  --nps 1e7 `
  --postprocess none
```

### CLI: prepare-workflow with built-in model (point_sdef_pos)

```powershell
python -m mcnp_research_skill.cli prepare-workflow `
  --builtin-model nai_3x3_verified `
  --work-dir runs/nai_point_sweep `
  --workflow-mode patch-and-run `
  --source-strategy point_sdef_pos `
  --source-position 0 0 20 `
  --source-energy 0.662 `
  --nps 1e7 `
  --postprocess none
```

> The `--builtin-model` flag is also accepted by `inspect-deck`,
> `plan-workflow`, `patch-deck`, and `run-workflow` as an alternative to
> `--input`.  When both are given, `--builtin-model` takes precedence.

---

## MCNP5 Compatibility Diagnostics

A static preflight check layer for MCNP5 input decks.  Does **not** simulate
or replace the MCNP5 parser — it identifies formatting, reference, and
consistency problems before execution.

### Supported version profiles

| Profile | Alias | Description |
|---------|-------|-------------|
| `mcnp5_rsicc_1_14` | `mcnp5_legacy` | Conservative legacy MCNP5 (RSICC 1.14 class): ≤80 columns, 5-space continuation, no tabs |

### What is checked

| Category | Issue Codes |
|----------|------------|
| Line length | `LINE_TOO_LONG` (columns > 80) |
| Tabs | `TAB_CHARACTER` |
| Card placement | `CARD_START_COLUMN` (card keyword not in cols 1-5) |
| Continuation | `INVALID_CONTINUATION` |
| Comments | `NON_ASCII_DATA_CARD`, `CHINESE_COMMENT_ENCODING_RISK` |
| Block structure | `MISSING_BLOCK_DELIMITER` |
| References | `UNKNOWN_TALLY_CELL_REFERENCE`, `UNKNOWN_SURFACE_REFERENCE`, `UNKNOWN_MATERIAL_REFERENCE` |
| Consistency | `MODE_TALLY_MISMATCH`, `MODE_SOURCE_MISMATCH` |

### Issue structure

Every diagnostic issue includes:

- `code` — stable issue code
- `severity` — `blocking` / `error` / `warning`
- `line` — 1-based line number
- `column` / `column_range` — optional
- `message` — one-line summary
- `mcnp_version` — which rule set was used
- `observed` — what was found
- `expected` — what the rule expects
- `auto_fixable` — whether `repair-deck` can fix this
- `suggested_fix` — human-readable suggestion
- `user_explanation` — Chinese explanation for the user
- `ai_guidance` — structured guidance for AI-assisted repair:
  - `mcnp_version_assumed`
  - `topics_to_review` — MCNP5 manual topics to consult
  - `instruction` — specific instruction in Chinese

### Repair boundaries

`repair-deck` only performs **safe format fixes**:

| Fix | Description |
|-----|-------------|
| tabs → spaces | Replace tab characters with 4-space-aligned spaces |
| long line → continuation | Split data-card lines at word boundaries before col 80 |
| bare CJK → comment | Prepend `c ` to bare Chinese lines |

The repair layer **does not** modify:
- Cell / surface geometry expressions
- Material compositions
- F tally definitions
- SDEF source physics
- MODE card
- NPS value

### Encoding / non-ASCII policy

- **Title card**: must be ASCII-only for MCNP5_RSICC 1.14 compatibility.
  Non-ASCII in the title line triggers `NON_ASCII_TITLE_CARD` (error).
  `repair-deck` replaces common Unicode punctuation (em dash → `--`, arrow → `->`, etc.) with ASCII equivalents.
- **Data/cell/surface cards**: must be ASCII-only.  Non-ASCII in card content
  triggers `NON_ASCII_DATA_CARD` (error).  Non-ASCII in `$` inline comments
  triggers a warning.  `repair-deck` does **not** auto-modify data card content.
- **Chinese in comment cards** (`c 中文...`): **allowed**, triggers
  `CHINESE_COMMENT_ENCODING_RISK` (warning, not blocking).
- **Bare Chinese lines** (outside comment cards): flagged as `NON_ASCII_DATA_CARD` (error).  `repair-deck` converts them to `c ...` format.
- **Safe punctuation mapping** (repair only; applies to title, c comments, and `$` inline comments):
  `—` → `--`, `–` → `-`, `→` → `->`, `←` → `<-`, `'`/`'` → `'`, `"`/`"` → `"`

### CLI: diagnose-deck

```powershell
# Diagnose a deck against legacy MCNP5 rules
python -m mcnp_research_skill.cli diagnose-deck --input A.txt

# Use built-in model
python -m mcnp_research_skill.cli diagnose-deck --builtin-model nai_3x3_verified

# Specify version
python -m mcnp_research_skill.cli diagnose-deck --input A.txt --mcnp-version mcnp5_rsicc_1_14
```

### CLI: repair-deck

```powershell
# Safe automatic format repair
python -m mcnp_research_skill.cli repair-deck --input A.txt --output repaired.txt

# Repaired text is written to --output; change log is in JSON stdout
```

### CLI: inspect-deck with diagnostics

```powershell
python -m mcnp_research_skill.cli inspect-deck --input A.txt --diagnostics
```

The output includes a `diagnostics` key with the full diagnostics result.

### CLI: prepare-workflow with diagnostics

```powershell
python -m mcnp_research_skill.cli prepare-workflow `
  --input A.txt --work-dir runs/w --workflow-mode run-only `
  --source-strategy preserve_existing_source --postprocess none `
  --diagnostics
```

- **Blocking issues** → `ok=false`, no prepared deck written
- **Warning/error only** → proceeds normally
- Without `--diagnostics` → diagnostics are not run (backward compatible)

### Workflow integration summary

| Command | `--diagnostics` | Effect |
|---------|----------------|--------|
| `inspect-deck` | optional | Adds `diagnostics` key to output |
| `prepare-workflow` | optional | Blocks on blocking issues |
| `diagnose-deck` | standalone | Full diagnostics JSON |
| `repair-deck` | standalone | Repaired file + change log |

### Boundaries

- **Not an MCNP5 parser**: this is static hygiene — it cannot detect all MCNP5 syntax errors.
- **Run-only unchanged**: `run-only` does not require F8; diagnostics do not add tally requirements.
- **CSV/plot unchanged**: non-F8 + csv/plot still returns `CSV_REQUIRES_F8`.
- **Safety gates unchanged**: `--execute --confirm-mpi --mpi-config` still required for real execution.
- **No physics changes**: repair never touches geometry, material, source, or tally definitions.
- **No automatic complex repairs**: continuation splitting is only attempted on data cards, not cell geometry lines.

---

## Natural-Language Request Planner

A deterministic rule-based parser that translates Chinese / English
natural-language workflow requests into structured plans.  **Not an
LLM** — pure regex and keyword matching.

### CLI: plan-request

```powershell
# Text input
python -m mcnp_research_skill.cli plan-request --text "用2英寸NaI，距离铝壳表面10到20厘米每步5厘米，Cs-137，nps 1e6"

# File input
python -m mcnp_research_skill.cli plan-request --text-file request.txt

# Override runtime check parameters
python -m mcnp_research_skill.cli plan-request --text "..." --np 8 --mpi-launcher mpiexec --mcnp-exe C:\MCNP\mcnp5mpi.exe
```

### Output

The planner outputs a structured JSON with:

| Field | Purpose |
|-------|---------|
| `human_summary` | User-facing Chinese explanation of what was understood |
| `confirmation_prompt` | Asks user to confirm before execution |
| `workflow_command` | Recommended CLI command (e.g., `run-point-sweep`) |
| `model` / `model_verified` | Detected model and verification status |
| `canonical_reference_point` | Resolved canonical reference point name |
| `nps` / `source_energy` / `postprocess` | Extracted parameters |
| `cli_preview` | Suggested CLI command lines |
| `runtime_preflight` | Environment check result |
| `can_execute_now` | Whether all pieces are ready for execution |
| `missing_required` | What's still missing |
| `warnings` / `errors` | Structured issues |

### Supported model aliases

| Alias | Resolves to |
|-------|-----------|
| `3 inch` / `3英寸` / `3x3 NaI` / `三英寸` | `nai_3x3_verified` |
| `2 inch` / `2英寸` / `2x2 NaI` / `二英寸` | `nai_2x2_template` |
| `1 inch` / `1英寸` / `1x1 NaI` / `一英寸` | `nai_1x1_template` |

### Supported reference point aliases

Three canonical reference points: `nai_crystal_front_surface`, `nai_crystal_center`, `aluminum_shell_front`.  Each has Chinese aliases (晶体前表面, 晶体中心, 铝壳表面).  Ambiguous aliases (晶体表面) return `AMBIGUOUS_REFERENCE_POINT`.

### How NPS / "源强度" is handled

- `源强度 1e7` or `10的7次方` → interpreted as **NPS (histories)**, **not** Bq activity
- Warning `SOURCE_STRENGTH_INTERPRETED_AS_NPS` is emitted
- `活度` / `activity` / `Bq` → `ACTIVITY_NORMALIZATION_UNSUPPORTED` error; activity normalization is not yet supported

### Boundaries

- Planner is **deterministic**, no external LLM/API calls
- Planner **only generates plans**, never executes MCNP
- `execute_requested=true` still requires user confirmation + safety gates
- Sweep source strategy defaults to `point_sdef_pos` if not specified

---

## Runtime Preflight / MPI Command Builder

Checks the local environment for MCNP/MPI readiness without executing anything.

### CLI: runtime-check

```powershell
python -m mcnp_research_skill.cli runtime-check
python -m mcnp_research_skill.cli runtime-check --np 8
python -m mcnp_research_skill.cli runtime-check --mpi-launcher mpiexec
python -m mcnp_research_skill.cli runtime-check --mcnp-exe C:\MCNP5\mcnp5mpi.exe
```

### What is checked

| Check | Detail |
|-------|--------|
| Logical processors | `os.cpu_count()` |
| Recommended `-np` | Default: `logical_processors + 1` (auto.py-compatible policy, **not** MPI standard) |
| MPI launcher | Searches PATH for `mpirun` / `mpiexec` |
| MCNP executable | Searches PATH for `mcnp5mpi` / `mcnp5` / `mcnp6` / `mcnp` |
| Command preview | `mpirun -np <n> mcnp5mpi` when both found |

### Boundaries

- `recommended_np = logical_processors + 1` is a heuristic, not a performance guarantee
- Users can override with `--np`, `--mpi-launcher`, `--mcnp-exe`
- Does **not** provide MCNP downloads or license workarounds
- If MCNP is not found, user is told to install a licensed copy and configure PATH

---

## Sweep CLI: --builtin-model + --reference-point

All four sweep commands now support both shortcuts:

```powershell
# --builtin-model instead of --input
python -m mcnp_research_skill.cli prepare-point-sweep `
  --builtin-model nai_2x2_template --work-dir runs/sweep `
  --start 10 --stop 20 --step 5 --source-energy 0.662 --nps 1e6

# --reference-point instead of --reference-position
python -m mcnp_research_skill.cli run-point-sweep `
  --builtin-model nai_3x3_verified --work-dir runs/sweep `
  --start 10 --stop 20 --step 5 --source-energy 0.662 --nps 1e6 `
  --reference-point nai_crystal_front_surface
```

Rules:
- `--input` and `--builtin-model` are mutually exclusive → `INPUT_CONFLICT`
- `--reference-point` and `--reference-position` are mutually exclusive → `REFERENCE_POSITION_CONFLICT`
- `--reference-point` requires `--builtin-model` for model-specific lookup

---

## Confirmation-Safe Execute Plan

### Two-step workflow

1. **plan-request**: Parse natural language → structured plan → `plan.json`
2. **execute-plan**: Read plan → validate → safe execution

The planner **never** executes MCNP directly.  The executor **defaults to
dry-run** and requires explicit user confirmation before real execution.

### Execution safety gates (all must pass)

| Gate | Requirement |
|------|-------------|
| Plan status | `ready_for_review` (not `blocked`/`needs_clarification`) |
| Required params | `missing_required` must be empty |
| User confirmation | `--confirm-user` flag |
| MCNP executable | Found on PATH or `--mcnp-exe` provided |
| MPI launcher | Found on PATH or `--mpi-launcher` provided |

### CLI: execute-plan

```powershell
# Dry-run (default): prepare decks only, no MCNP
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json

# Execute with user confirmation
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json --execute --confirm-user

# NP override
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json --execute --confirm-user --np 8

# MPI launcher / MCNP exe override
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json --execute --confirm-user `
  --mpi-launcher mpiexec --mcnp-exe C:\MCNP5\mcnp5mpi.exe

# Expert: full MPI command override
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json --execute --confirm-user `
  --mpi-command "mpirun -np 8 mcnp5mpi.exe"
```

### Plan → workflow mapping

| `workflow_command` | Calls |
|--------------------|-------|
| `prepare-point-sweep` | `prepare_point_sweep()` |
| `run-point-sweep` | `run_point_sweep()` |
| `prepare-disk-sweep` | `prepare_disk_sweep()` |
| `run-disk-sweep` | `run_disk_sweep()` |
| `run-workflow` | `run_workflow()` |
| `diagnose-deck` | `diagnose_deck_file()` |
| Unsupported | `PLAN_COMMAND_UNSUPPORTED` |

### Complete example

```powershell
# Step 1: Parse natural language
python -m mcnp_research_skill.cli plan-request `
  --text "用2英寸NaI，距离铝壳表面10到20厘米每步5厘米，Cs-137，NPS=1e7，只出CSV" `
  --output plan.json

# Step 2: AI shows human_summary and command_preview to user

# Step 3: User confirms, then execute
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json `
  --execute --confirm-user --np 8 `
  --mpi-launcher mpirun --mcnp-exe mcnp5mpi.exe
```

### Error codes

| Code | Meaning |
|------|---------|
| `USER_CONFIRMATION_REQUIRED` | `--execute` without `--confirm-user` |
| `PLAN_NOT_EXECUTABLE` | Plan status is blocked/needs_clarification |
| `PLAN_MISSING_REQUIRED` | Plan has missing required parameters |
| `PLAN_COMMAND_UNSUPPORTED` | workflow_command not yet mappable |
| `MCNP_NOT_FOUND` | MCNP executable not found |
| `MPI_LAUNCHER_NOT_FOUND` | MPI launcher not found |
| `PLAN_FILE_INVALID` | Plan file is not valid JSON |
| `PLAN_FILE_NOT_FOUND` | Plan file does not exist |

### Boundaries

- `recommended_np = logical_processors + 1` is auto.py-compatible, not MPI standard
- `--mpi-command` is an **expert override**; the recommended path is `--mpi-launcher` + `--mcnp-exe` + `--np`
- MPI command source (`user_override` vs `runtime_preflight`) is recorded
- Does **not** provide MCNP downloads or license workarounds
- `execute_requested=true` in the plan is **not sufficient** for real execution; `--confirm-user` is always required
