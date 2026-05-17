# Release Notes: v0.4.0-beta

`v0.4.0-beta` is a release-freeze snapshot for `mcnp-research-skill` as an AI-callable MCNP5 workflow skill.

This release focuses on packaging the project as a stable beta: documentation, CI, wheel install smoke tests, model cards, AI usage contract, error-code contract, and real MCNP validation guidance.

## Release status

| Item | Status |
|---|---|
| Package version | `0.4.0b1` |
| CI | GitHub Actions green on Windows / Python 3.10, 3.11, 3.12 |
| Test policy | Unit/acceptance tests do not run real MCNP/MPI |
| Wheel smoke test | Builds a wheel, installs it in a clean venv, checks CLI and built-in model access |
| Default user output | Chinese text |
| Automation output | `--json` |
| Execution default | dry-run |
| Real execution gate | `--execute --confirm-user` |

## Main capabilities

### Natural-language workflow planning

- Chinese and English deterministic planner.
- Detects NaI detector size, source energy, NPS, distance range/step, postprocess intent, source strategy, and execution intent.
- Uses Chinese user-facing summaries by default.
- Uses `--json` for automation and AI wrappers.

### Built-in NaI models

- `nai_3x3_verified`: verified model derived from the A.txt fixture.
- `nai_2x2_template`: unverified 2x2 template.
- `nai_1x1_template`: unverified 1x1 template.

Model cards document source, assumptions, reference points, verified status, and safety boundaries.

### MCNP5_RSICC 1.14 diagnostics

- 80-column checks.
- Tab and continuation checks.
- Comment-card and non-ASCII risk checks.
- Cell/surface/material/tally/source reference checks.
- Guided repair only for safe formatting issues.

### Runtime preflight and execution safety

- Detects MCNP executable and MPI launcher.
- Reports `MCNP_NOT_FOUND` and `MPI_LAUNCHER_NOT_FOUND` clearly.
- Recommends `logical_processors + 1` as the legacy `auto.py` policy, not an MPI standard.
- Keeps real execution behind `--execute --confirm-user`.

### Run failure analysis

- Analyzes MCNP output/stdout/stderr after failed execution.
- Prioritizes the first 300 lines of MCNP output to avoid sending huge logs through the AI layer.
- Provides likely cause and safe next-step guidance.

### SPE to GEB workflow

- Fits GEB A/B/C from SPE files.
- Patches `FT8 GEB` without overwriting the original input deck.
- Blocks GEB patching for non-F8 decks.
- Requires fit quality and user review before patch/run.

### F8 and non-F8 boundary

- F8 supports CSV extraction, plotting, and FT8 GEB.
- F2/F4/F5/F6/FMESH may be inspected, diagnosed, prepared, run, batched, and swept.
- Non-F8 CSV/plot returns `CSV_REQUIRES_F8`.

## New release-hardening documents

- `docs/ai_usage_contract.md`
- `docs/error_codes.md`
- `docs/real_mcnp_validation.md`
- `docs/models/nai_3x3_verified.md`
- `docs/models/nai_2x2_template.md`
- `docs/models/nai_1x1_template.md`
- `docs/final_freeze_checklist.md`

## Known limitations

- CI and unit tests do not run real MCNP/MPI.
- The project does not provide MCNP downloads, cracks, licenses, or authorization bypass instructions.
- Bq/activity normalization is not implemented.
- F2/F4/F5/F6/FMESH postprocess extractors are not implemented.
- The natural-language planner is deterministic and rule-based, not an LLM.
- 1x1 and 2x2 NaI decks are unverified templates.
- GEB fitting is a workflow integration, not a full spectroscopy analysis package.

## Recommended validation before real use

1. Run the full test suite.
2. Run the wheel smoke test or confirm GitHub Actions is green.
3. Run `runtime-check` on the target workstation.
4. Run `diagnose-deck` on the target deck.
5. Run `execute-plan` dry-run.
6. Confirm the command preview.
7. Use `--execute --confirm-user` only after review.
8. Analyze failures with `analyze-run-failure`.

## Suggested tag

After CI is green on this release-freeze state, create a Git tag:

```powershell
git tag v0.4.0-beta
git push origin v0.4.0-beta
```

The GitHub connector used in this session does not expose a dedicated tag/release creation tool, so tag creation should be done locally or through the GitHub UI/API.
