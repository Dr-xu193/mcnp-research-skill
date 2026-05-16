# Error Code Reference

This document is the user-facing and AI-facing contract for common `mcnp-research-skill` error codes.

Fields:

- **Blocking**: the workflow should stop until the issue is resolved.
- **Auto-fixable**: the skill may safely repair the issue without changing physics.
- **User action**: what the user or AI wrapper should do next.

## Planning and natural-language parsing

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `MISSING_MODEL_OR_INPUT` | No built-in model or input deck was provided. | Yes | No | Provide a built-in model id or an MCNP input deck. |
| `MISSING_SOURCE_ENERGY` | Source energy was not specified or inferred. | Yes | No | Provide energy in MeV/keV or a supported isotope name. |
| `MISSING_SOURCE_RADIUS` | `disk_tr1` source strategy needs a source radius. | Yes | No | Provide `source_radius` in cm. |
| `MISSING_SOURCE_POSITION` | Source position could not be determined. | Yes | No | Provide reference point and distance, or explicit position. |
| `AMBIGUOUS_REFERENCE_POINT` | The reference point phrase is ambiguous, such as “晶体表面” or “距离探测器”. | Yes | No | Choose `aluminum_shell_front`, `nai_crystal_front_surface`, or `nai_crystal_center`. |
| `UNKNOWN_REFERENCE_POINT` | The requested reference point name is unknown. | Yes | No | Use one of the canonical reference point names. |
| `INVALID_DISTANCE_STEP` | Distance step is zero, negative, or invalid. | Yes | No | Provide a positive step, for example `每步 0.5 cm`. |
| `UNIT_ASSUMED_CM` | A distance unit was omitted and cm was assumed. | No | No | Confirm the intended unit if cm is not correct. |
| `SOURCE_STRENGTH_INTERPRETED_AS_NPS` | A phrase such as “source strength 1e7” was interpreted as MCNP histories. | No | No | Confirm this is NPS/histories, not activity. |
| `ACTIVITY_NORMALIZATION_UNSUPPORTED` | Bq/activity was requested but cannot be directly mapped to NPS. | Yes | No | Provide NPS or a separate activity-normalization method. |
| `PLAN_MISSING_REQUIRED` | The plan is missing one or more required fields. | Yes | No | Read `missing_required` and provide the missing items. |
| `PLAN_NOT_EXECUTABLE` | The plan cannot be executed safely. | Yes | No | Resolve blocking errors before execution. |

## Built-in models and file roles

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `MODEL_NOT_FOUND` | Requested built-in model id does not exist. | Yes | No | Run `models list` and choose a valid model. |
| `MISSING_INPUT_DECK` | A workflow needs a target MCNP input deck, but none was provided. | Yes | No | Provide `.txt`, `.inp`, `.i`, or `.mcnp` deck. |
| `FILE_ROLE_AMBIGUOUS` | Provided files cannot be safely classified. | Yes | No | Identify which files are SPE spectra, MCNP decks, profiles, or context files. |
| `INPUT_DECK_AMBIGUOUS` | More than one possible input deck was provided. | Yes | No | Choose the deck that should be patched or run. |
| `MISSING_SPE_FILES` | A GEB workflow needs SPE files, but none were provided. | Yes | No | Provide at least three SPE files or explicit peak data. |

## MCNP5_RSICC 1.14 deck diagnostics

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `LINE_TOO_LONG` | A card exceeds the MCNP5 legacy line-length limit. | Usually | Sometimes | Run `repair-deck` only for safe formatting cases, otherwise review manually. |
| `TAB_CHARACTER` | A tab character was found. | Usually | Yes | Replace tabs with spaces via `repair-deck`. |
| `INVALID_CONTINUATION` | Continuation formatting is invalid or risky. | Yes | Sometimes | Review the card under MCNP5_RSICC 1.14 rules. |
| `NON_ASCII_TITLE_CARD` | The title card contains non-ASCII text. | Warning/Yes | Sometimes | Convert to ASCII if MCNP5 rejects it. |
| `NON_ASCII_DATA_CARD` | A data card contains non-ASCII text. | Yes | Sometimes | Remove/convert non-ASCII characters. |
| `CHINESE_COMMENT_ENCODING_RISK` | Chinese comment content may fail on old MCNP5/Windows encodings. | Warning | Sometimes | Use valid MCNP comment cards and test with the target MCNP5 build. |
| `CELL_SURFACE_REFERENCE_ERROR` | A cell references an undefined or invalid surface. | Yes | No | Check cell Boolean expressions and surface ids. |
| `TALLY_REFERENCE_ERROR` | A tally references a missing cell/surface or invalid entity. | Yes | No | Check F card targets. |
| `MODE_PARTICLE_MISMATCH` | MODE card does not include source/tally particle type. | Yes | No | Update MODE intentionally after reviewing source and tally cards. |

## Runtime and execution

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `USER_CONFIRMATION_REQUIRED` | Real execution was requested without explicit confirmation. | Yes | No | Re-run with `--execute --confirm-user` after reviewing the plan. |
| `MCNP_NOT_FOUND` | MCNP executable was not found by runtime preflight. | Yes | No | Install/configure legally licensed MCNP or pass `--mcnp-exe`. |
| `MCNP_EXECUTABLE_NOT_FOUND` | MCNP executable could not be launched or located. | Yes | No | Check executable path and permissions. |
| `MPI_LAUNCHER_NOT_FOUND` | `mpirun`/`mpiexec` was not found. | Yes | No | Install/configure MPICH/OpenMPI or pass `--mpi-launcher`. |
| `RUNTIME_PERMISSION_DENIED` | Runtime command cannot be executed due to permissions. | Yes | No | Fix file permissions or run from an allowed location. |
| `RUNTIME_COMMAND_FAILED` | Runtime command failed without a more specific classification. | Yes | No | Inspect stdout/stderr and run `analyze-run-failure`. |
| `MPI_PROCESS_FAILED` | MPI launch or MPI process failed. | Yes | No | Check MPI installation, working directory, and MCNP command. |

## Postprocessing and tally support

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `CSV_REQUIRES_F8` | CSV/plot postprocessing was requested for a non-F8 deck. | Yes for CSV/plot | No | Continue run-only, or use an F8 pulse-height tally. |
| `MISSING_MCNP_OUTPUT` | Postprocessing was requested but MCNP output path is missing. | Yes | No | Provide output file path or run MCNP first. |
| `UNSUPPORTED_TALLY_FOR_POSTPROCESS` | Requested postprocess is not implemented for the tally type. | Yes for postprocess | No | Use run-only or implement a tally-specific extractor. |

## MCNP run failure analysis

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `MCNP_FATAL_ERROR` | MCNP reported a fatal error. | Yes | No | Review the evidence excerpt and run `diagnose-deck`. |
| `MCNP_INPUT_FORMAT_ERROR` | MCNP reported input/card formatting failure. | Yes | Sometimes | Check 80 columns, continuation, tabs, comments, and non-ASCII cards. |
| `MCNP_UNKNOWN_SURFACE` | MCNP reported an unknown or undefined surface. | Yes | No | Check surface ids and cell Boolean expressions. |
| `MCNP_UNKNOWN_CELL` | MCNP reported an unknown or undefined cell. | Yes | No | Check cell ids and tally/source references. |
| `MCNP_GEOMETRY_ERROR` | MCNP reported geometry trouble. | Yes | No | Inspect cells, surfaces, overlaps, and voids manually. |
| `MCNP_LOST_PARTICLE` | Lost particles or geometry tracking failure were reported. | Yes/Warning | No | Check geometry boundaries and source placement. |
| `MCNP_XS_LIBRARY_NOT_FOUND` | Cross-section library or `xsdir` data was not found. | Yes | No | Configure a valid licensed MCNP data library. |
| `MCNP_SOURCE_ERROR` | MCNP reported a source/SDEF/SI/SP/TR issue. | Yes | No | Check generated or user source cards. |
| `MCNP_MODE_PARTICLE_MISMATCH` | Source/tally particles are inconsistent with MODE. | Yes | No | Review MODE, source particle, and tally particle settings. |

## SPE to GEB workflow

| Code | Meaning | Blocking | Auto-fixable | User action |
|---|---|:---:|:---:|---|
| `MISSING_NUCLIDE_ENERGY` | Peak energy cannot be inferred for SPE fitting. | Yes | No | Provide nuclide energy, ROI, or profile. |
| `NEEDS_PEAK_RANGE` | SPE peak ROI/range is required. | Yes | No | Provide `--peak-range` or a profile. |
| `GEB_FIT_INSUFFICIENT_PEAKS` | Fewer than 3 accepted peaks are available for A/B/C fit. | Yes | No | Provide more SPE files or better peak/ROI settings. |
| `GEB_FIT_FAILED` | GEB fitting failed. | Yes | No | Review SPE data, expected energies, and ROI. |
| `GEB_REQUIRES_F8` | FT8 GEB patching requires an F8 pulse-height tally. | Yes for patch | No | Use an F8 deck or keep non-F8 run-only. |
| `GEB_PATCH_BLOCKED` | GEB patch was blocked by safety/diagnostics. | Yes | No | Resolve the reported reason before patching. |
| `GEB_PATCH_REQUIRES_CONFIRMATION` | GEB patch requires user confirmation. | Yes | No | Review fit quality and confirm patching. |

## Safety notes

- “Auto-fixable” never means changing detector geometry, material definitions, tally physics, or source physics automatically.
- Do not provide MCNP downloads, cracks, licenses, or authorization bypass guidance.
- For ambiguous physical meaning, ask the user instead of guessing.
