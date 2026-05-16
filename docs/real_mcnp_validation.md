# Real MCNP / MPICH Validation Guide

This guide describes how a user can validate `mcnp-research-skill` on a real local MCNP/MPICH installation.

The normal test suite and GitHub Actions do **not** run real MCNP/MPI. Real execution must be performed manually on a properly licensed local environment.

## Scope

This guide covers:

- checking whether MCNP and MPICH/OpenMPI are visible
- generating a dry-run plan
- reviewing the command preview
- running a confirmed execution
- diagnosing failure output

This guide does not provide MCNP downloads, license bypasses, cracks, or installation packages.

## Prerequisites

You need:

1. A legally available MCNP executable, for example `mcnp5mpi.exe`, `mcnp5`, `mcnp6`, or `mcnp`.
2. An MPI launcher, for example `mpirun` or `mpiexec`.
3. A working command shell where both tools can be called.
4. A deck that passes basic MCNP5 diagnostics.

On Windows, confirm commands in PowerShell:

```powershell
where mpirun
where mpiexec
where mcnp5mpi
where mcnp5
where mcnp6
```

If these commands do not resolve, pass explicit paths to the CLI or fix your environment variables.

## Step 1: Runtime check

Run:

```powershell
python -m mcnp_research_skill.cli runtime-check
```

Expected result:

- CPU logical processor count is shown
- recommended NP is shown as `logical_processors + 1`
- MPI launcher status is shown
- MCNP executable status is shown

`logical_processors + 1` follows the legacy `auto.py` policy. It is not an MPI standard. Override it if your local environment requires a different process count.

## Step 2: Diagnose the input deck

For a user-provided deck:

```powershell
python -m mcnp_research_skill.cli diagnose-deck --input A.txt --mcnp-version mcnp5_rsicc_1_14
```

Fix blocking issues before execution. Typical MCNP5_RSICC 1.14 checks include:

- 80-column line limit
- tab characters
- continuation formatting
- comment-card format
- non-ASCII title/data-card risk
- cell/surface/material/tally/source references

Use `repair-deck` only for safe formatting issues. Do not auto-fix geometry, material definitions, tally physics, or source physics.

## Step 3: Create a plan from natural language

Example:

```powershell
python -m mcnp_research_skill.cli plan-request `
  --text "用3英寸NaI，Cs-137点源，距离NaI晶体前表面10到20厘米，每步5厘米，NPS=1e6，只出CSV" `
  --output plan.json
```

Review the Chinese output. Confirm:

- model or input deck
- source energy
- NPS
- distance values
- reference point
- source strategy
- postprocess intent
- missing or ambiguous fields

If the output says a reference point is ambiguous, choose one of:

- `aluminum_shell_front`
- `nai_crystal_front_surface`
- `nai_crystal_center`

## Step 4: Dry-run execution

Run:

```powershell
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json
```

This should not run MCNP. It should show the prepared workflow and command preview, if runtime tools are found.

If MCNP or MPI is missing, the output should explain:

- `MCNP_NOT_FOUND`
- `MPI_LAUNCHER_NOT_FOUND`

Provide explicit paths when needed:

```powershell
python -m mcnp_research_skill.cli execute-plan `
  --plan-file plan.json `
  --mcnp-exe "C:\path\to\mcnp5mpi.exe" `
  --mpi-launcher "C:\path\to\mpirun.exe"
```

## Step 5: Confirmed real execution

After reviewing the dry-run output and command preview, run real execution only with explicit confirmation:

```powershell
python -m mcnp_research_skill.cli execute-plan `
  --plan-file plan.json `
  --execute `
  --confirm-user
```

Optional overrides:

```powershell
python -m mcnp_research_skill.cli execute-plan `
  --plan-file plan.json `
  --execute `
  --confirm-user `
  --np 9 `
  --mcnp-exe "C:\path\to\mcnp5mpi.exe" `
  --mpi-launcher "C:\path\to\mpirun.exe"
```

Do not hard-code `-np 17` for every user. The process count depends on the local machine and can be overridden.

## Step 6: Failure analysis

If MCNP or MPI fails, analyze the output:

```powershell
python -m mcnp_research_skill.cli analyze-run-failure `
  --output o.txt `
  --stderr stderr.txt `
  --context plan.json
```

Default behavior:

- prioritize the first 300 lines of MCNP output
- do not display the entire output file
- use stderr/stdout/tail only when the front section is insufficient
- explain likely MCNP5 input, geometry, material, source, tally, MODE, or runtime problems

## Minimal validation checklist

A real local environment is ready when all of the following are true:

- `runtime-check` finds MPI and MCNP, or explicit paths are accepted
- `diagnose-deck` has no blocking MCNP5 issues
- `execute-plan` dry-run succeeds
- command preview matches the expected local command
- real execution only occurs after `--execute --confirm-user`
- failed runs can be passed to `analyze-run-failure`

## Safety boundaries

- Do not run real MCNP/MPI in GitHub Actions or ordinary unit tests.
- Do not provide MCNP downloads, cracks, license bypasses, or unauthorized installation instructions.
- Do not treat Bq activity as NPS.
- Do not silently change detector geometry, material cards, F cards, source physics, or tally physics.
- Non-F8 decks can run, but CSV/plot and FT8 GEB workflows require F8 pulse-height tally.
