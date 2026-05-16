# AI Usage Contract

This document defines how an AI assistant should call `mcnp-research-skill` safely and consistently.

## Core rule

Default user-facing output should be Chinese text. Use `--json` internally for automation, validation, and tool chaining.

Do not run MCNP/MPI unless the user has explicitly confirmed execution. Tests and normal CI must not run real MCNP/MPI.

## Recommended AI workflow

1. Parse the user request with `plan-request`.
2. Show the Chinese understanding and mapping to the user.
3. If required information is missing or ambiguous, ask for the specific missing item.
4. Run `diagnose-deck` for user-provided decks or patched decks.
5. Run `runtime-check` before any real execution.
6. Use `execute-plan` dry-run by default.
7. Only use `--execute --confirm-user` after explicit user confirmation.
8. If execution fails and output files exist, call `analyze-run-failure`.

## Natural-language requests

The AI should map common Chinese and English requests into structured workflow fields:

- detector model: `nai_3x3_verified`, `nai_2x2_template`, `nai_1x1_template`, or user deck
- source energy in MeV
- NPS histories, not Bq activity
- distance range and step in cm
- reference point
- source strategy
- postprocess intent
- execution intent

If the user says “距离探测器” or “晶体表面” and the reference point is not explicit, return or explain `AMBIGUOUS_REFERENCE_POINT` rather than guessing.

## File role handling

When multiple files are provided, infer roles conservatively:

- `.spe`, `.SPE`, `.Spe`: SPE spectrum files for GEB fitting
- `.txt`, `.inp`, `.i`, `.mcnp`: possible MCNP input deck after deck inspection
- `.json`, `.yaml`, `.yml`: plan, profile, or context file
- unknown extension: ask the user to identify the file role

Do not silently treat arbitrary `.txt` files as SPE files.

## MCNP5 deck diagnostics

For user-provided or generated decks, prefer `mcnp5_rsicc_1_14` checks. Explain the following to the user when relevant:

- 80-column line limit
- tabs
- continuation formatting
- comment-card rules
- Chinese comments and non-ASCII risks
- cell/surface/material/tally/source reference issues

`repair-deck` may only fix safe formatting problems. It must not modify geometry, material cards, F cards, tally physics, or source physics without explicit user review.

## Runtime preflight

Before real execution, call `runtime-check` or use the runtime preflight inside `execute-plan`.

Explain missing tools clearly:

- missing MCNP executable: install legally licensed MCNP or pass `--mcnp-exe`
- missing MPI launcher: install/configure MPICH/OpenMPI or pass `--mpi-launcher`

Recommended MPI process count follows the legacy `auto.py` policy: `logical_processors + 1`. This is not an MPI standard and may be overridden.

## Execution safety

`execute-plan` must remain dry-run by default.

Real execution requires both:

- `--execute`
- `--confirm-user`

Never bypass this gate for natural-language requests such as “直接运行”. Show the planned command and ask for confirmation.

## F8 and non-F8 boundary

F8 pulse-height tally supports CSV extraction and plotting.

F2/F4/F5/F6/FMESH decks may still be inspected, diagnosed, prepared, run, batched, or swept, but CSV/plot postprocessing is blocked.

If the user requests CSV/plot for a non-F8 deck, return or explain `CSV_REQUIRES_F8` and offer run-only as the safe alternative.

## SPE to GEB workflow

If the user asks to derive, fit, calculate, or calibrate GEB from SPE/spectrum files:

1. identify SPE files and the target MCNP deck
2. fit GEB A/B/C
3. show accepted/rejected peaks and fit quality
4. do not patch if fit quality is insufficient
5. patch only `FT8 GEB` and only for F8 decks
6. do not overwrite the original deck
7. diagnose the patched deck before sweep/run

If fewer than 3 accepted peaks are available, explain `GEB_FIT_INSUFFICIENT_PEAKS` and ask for more SPE files or explicit peak energy/ROI information.

## Run failure analysis

After a failed run, use `analyze-run-failure` with output/stdout/stderr/context if available.

Default analysis should prioritize the first 300 lines of MCNP output. Do not paste or summarize entire multi-thousand-line outputs unless specifically requested. If the first 300 lines are insufficient, use stderr/stdout/tail summaries.

## What not to do

- Do not provide MCNP downloads, cracks, licenses, or authorization bypass instructions.
- Do not assume Bq activity equals NPS.
- Do not treat 1x1/2x2 templates as verified detector models.
- Do not silently pick a reference point when the user is ambiguous.
- Do not modify geometry/material/source/tally physics automatically.
- Do not require ordinary users to hand-write `mpi_config.yaml` for basic execution.
- Do not run real MCNP/MPI in CI.

## Expected assistant response style

For ordinary users, summarize:

- what was understood
- what will be changed
- what is missing or ambiguous
- whether the plan is executable
- whether MCNP/MPICH is available
- the safe next step

Use JSON only when acting as an internal automation layer or when the user explicitly asks for structured output.
