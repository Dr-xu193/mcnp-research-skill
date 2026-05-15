# User Scenarios

End-to-end natural-language → plan → execute workflows.

## Two-step workflow

1. **plan-request** — parse natural language into a structured plan
2. **execute-plan** — validate, confirm, and safely execute (default dry-run)

The planner never executes MCNP directly.  The executor always requires
`--confirm-user` for real execution.

---

## Scenario 1: Verified 3x3 NaI, crystal front sweep

**User says:**
> 3 inch NaI, distance from nai crystal front surface 10 to 20 cm step 5 cm, nps 1e6, Cs-137, csv only

**What happens:**
- Model: `nai_3x3_verified` (verified=true)
- Reference: `nai_crystal_front_surface` at [0, 0, 0] (verified, from A.txt surface 14)
- Distances: 10, 15, 20 cm
- NPS: 1,000,000
- Energy: 0.662 MeV (Cs-137)
- Postprocess: CSV only, no plot
- Source: point_sdef_pos (default, with warning)

**CLI:**
```powershell
python -m mcnp_research_skill.cli plan-request `
  --text "3 inch NaI, distance from nai crystal front surface 10 to 20 cm step 5 cm, nps 1e6, Cs-137, csv only" `
  --output plan.json

python -m mcnp_research_skill.cli execute-plan --plan-file plan.json
```

---

## Scenario 2: 2x2 template, aluminum shell sweep, execute requested

**User says:**
> 2 inch NaI, nps 1e7, distance from aluminum shell 10 to 20 cm step 5 cm, execute and csv

**What happens:**
- Model: `nai_2x2_template` (verified=false, template)
- Reference: `aluminum_shell_front` at [0, 0, -0.1] (template assumption, not verified)
- NPS: 10,000,000
- execute_requested=true, but source_energy missing → blocked
- human_summary warns: template, assumption, NPS ≠ Bq

**CLI:**
```powershell
python -m mcnp_research_skill.cli plan-request `
  --text "2 inch NaI, Cs-137 point source, distance from aluminum shell 10 to 20 cm step 5 cm, nps 1e7, csv only, execute" `
  --output plan.json

# Without confirmation → USER_CONFIRMATION_REQUIRED
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json --execute

# With confirmation
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json --execute --confirm-user
```

---

## Scenario 3: 1x1 template, crystal center sweep

**User says:**
> 1 inch NaI, point source, distances 5 10 15 cm from crystal center, Cs-137, nps 1e6, prepare only

**What happens:**
- Model: `nai_1x1_template`
- Reference: `nai_crystal_center` at [0, 0, 1.27]
- Distances: 5, 10, 15 cm
- Source positions computed as 1.27 + distance along z
- intent=prepare_sweep

---

## Scenario 4: Ambiguous crystal surface

**User says:**
> 3 inch NaI, distance from crystal surface 10 cm, nps 1e6

**What happens:**
- `AMBIGUOUS_REFERENCE_POINT` error
- User is prompted to choose:
  - `nai_crystal_front_surface` (crystal front)
  - `nai_crystal_center` (crystal center)
  - `aluminum_shell_front` (aluminum housing front)
- No deck generated

---

## Scenario 5: Disk source with radius

**User says:**
> 2 inch NaI, disk source, radius 0.15 cm, distance from aluminum shell 10 to 20 cm step 5 cm, Cs-137, nps 1e7, csv only

**What happens:**
- source_strategy=disk_tr1, source_radius=0.15
- Runs disk sweep dry-run successfully
- TR/SI/SP cards generated with auto card-id

---

## Scenario 6: Activity Bq ≠ NPS

**User says:**
> 2 inch NaI, Cs-137 activity 1e6 Bq, distance from crystal front 10 cm, run csv

**What happens:**
- `ACTIVITY_NORMALIZATION_UNSUPPORTED` error
- 1e6 Bq is NOT mapped to nps
- human_summary explains activity-to-count-rate normalization is not supported

---

## Scenario 7: Runtime missing MCNP

**User says:**
> 2 inch NaI, Cs-137 point source, distance from aluminum shell 10 cm, nps 1e6, execute

**What happens:**
- plan-request succeeds
- execute-plan with --confirm-user --execute returns `MCNP_NOT_FOUND`
- User is told to install a licensed MCNP distribution and configure PATH
- No download/workaround provided

---

## Scenario 8: Runtime missing MPI launcher

**User says:**
> 2 inch NaI, Cs-137 point source, distance from aluminum shell 10 cm, nps 1e6, execute

**What happens:**
- execute-plan returns `MPI_LAUNCHER_NOT_FOUND`
- User is told to install MPICH/OpenMPI or specify --mpi-launcher

---

## Scenario 9: MCNP5 diagnostics

**User says:**
> diagnose this deck for MCNP5_RSICC 1.14 compatibility

**What happens:**
- intent=diagnose_deck
- diagnose-deck outputs structured issues (LINE_TOO_LONG, TAB_CHARACTER, etc.)
- Each issue includes: code, severity, line, suggested_fix, ai_guidance

---

## Reference points summary

| Canonical name | Alias examples | 3x3 (verified) | 1x1 (template) | 2x2 (template) |
|---------------|---------------|--------|--------|--------|
| `nai_crystal_front_surface` | crystal_front, 晶体前表面 | [0,0,0] ✓ | [0,0,0] ✗ | [0,0,0] ✗ |
| `nai_crystal_center` | crystal_center, 晶体中心 | [0,0,3.81] ✓ | [0,0,1.27] ✗ | [0,0,2.54] ✗ |
| `aluminum_shell_front` | aluminum_shell, 铝壳表面 | [0,0,-0.34] ✓ | [0,0,-0.1] ✗ | [0,0,-0.1] ✗ |

✓ = verified from A.txt fixture
✗ = template assumption, user must validate

---

## Model status

| Model | Verified | Status | Validated reference points |
|-------|----------|--------|---------------------------|
| `nai_3x3_verified` | Yes | verified | All 3 (from A.txt) |
| `nai_2x2_template` | No | template | None (user must validate) |
| `nai_1x1_template` | No | template | None (user must validate) |

---

## Safety gates

| Gate | Required for real execution |
|------|---------------------------|
| plan-request `--output` | No (plan only) |
| execute-plan dry-run | No (prepare decks only) |
| `--execute` | Yes |
| `--confirm-user` | Yes |
| MCNP found or `--mcnp-exe` | Yes |
| MPI found or `--mpi-launcher` | Yes |
| `--mpi-command` (expert override) | Alternative |

---

## Boundaries

- The planner is a deterministic rule-based parser, not an LLM.
- It generates structured plans only; never executes MCNP directly.
- `recommended_np = logical_processors + 1` is auto.py-compatible, not an MPI standard.
- Does not provide MCNP downloads or license workarounds.
- Does not support activity-to-count-rate normalization (Bq → NPS).
- F4/F5/F6 tallies are detectable but csv/plot only supports F8.
- run-only mode does not require F8.
