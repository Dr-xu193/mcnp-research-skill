# Changelog

## [0.4.0-beta] — 2026-05-15

### Added
- **SPE to GEB workflow integration** — fit GEB A/B/C from SPE files and patch FT8 GEB without overwriting the original deck.
- **GEB patching** — `patch-deck --geb A B C` inserts or replaces `FT8 GEB` only when an F8 pulse-height tally exists.
- **GEB workflow planning** — natural-language aliases for deriving GEB parameters from SPE/spectrum files, writing GEB cards, and continuing to distance sweep workflows.
- **GEB execution dispatch** — `execute-plan` supports `fit_geb`, `fit_geb_and_patch`, and `fit_geb_patch_and_run_sweep` dry-run/mock workflows.
- **Chinese distance/NPS robustness** — decimal distance ranges, decimal steps, `mm -> cm`, `10的7次方`, superscript powers, and keV decimal energies.
- **Release documentation files** — `AGENTS.md` and `.agents/skills/mcnp-research-pipeline/SKILL.md` restored for skill/test compliance.
- **Package data metadata** — built-in model fixtures are declared as package data.

### Changed
- README and package metadata updated for v0.4.0-beta, 748 tests, GEB workflow, and CI-green state.
- CI runtime tests now aggregate concrete runtime preflight errors such as `MCNP_NOT_FOUND` and `MPI_LAUNCHER_NOT_FOUND`.
- CLI subprocess tests no longer rely on parent-process mocks for runtime discovery.

### Fixed
- `execute-plan` no longer drops `MPI_LAUNCHER_NOT_FOUND` when MCNP is also missing.
- Windows GitHub Actions tests are stable across Python 3.10, 3.11, and 3.12.
- `fit-geb-from-spe` CLI tests use `--json` when structured output is required.

---

## [0.3.0] — 2026-05-15

### Added
- **Natural-language workflow planner** — Chinese/English request parsing, model detection, parameter extraction, human-readable summary output
- **Confirmation-safe execute-plan** — five security gates, dry-run by default, user confirmation required
- **Runtime preflight** — CPU/core detection, MPI launcher search, MCNP executable search, command preview
- **Named reference points** — 3 canonical points per model, 40+ Chinese/English aliases, ambiguous alias detection
- **MCNP5 front-of-output failure analyzer** — first-300-line analysis, 18 error categories, context-aware suggestions
- **User-facing Chinese renderer** — all user commands output Chinese text by default, `--json` for automation
- **Built-in model registry** — `nai_3x3_verified`, `nai_1x1_template`, `nai_2x2_template` with reference point metadata

### Changed
- Default CLI output is now Chinese text; use `--json` for structured JSON
- Sweep commands now support `--builtin-model` and `--reference-point`
- plan-request now supports `--output` for saving plans to file
- pyproject.toml version updated to 0.3.0

### Fixed
- MCNP5_RSICC 1.14 input encoding checks for title/data cards
- Unicode punctuation (em dash, arrow) replaced with ASCII in template decks
- POSSIBLE_UNUSED_SOURCE_CARDS warning now propagated correctly through prepare_workflow

---

## [0.2.0] — 2026-05-14

### Added
- **MCNP5 compatibility diagnostics** — 80-column check, tab detection, continuation validation, reference checking, MODE/tally consistency
- **Guided repair layer** — safe auto-fix for tabs, long lines, Unicode punctuation, bare Chinese comments
- **Source strategy v1** — `preserve_existing_source`, `point_sdef_pos`, `disk_tr1`
- **Point source sweep** — prepare and run distance sweeps with point sources
- **Disk source sweep** — prepare and run distance sweeps with disk (TR1) sources
- **F8 postprocess workflow** — CSV extraction and spectrum plotting
- **Batch workflow** — batch prepare/run for directories of `.txt` decks
- **Built-in model** — verified 3x3 NaI(Tl) deck from A.txt fixture
- **Profiles system** — YAML-based user configuration at `~/.mcnp-research/profiles.yaml`
- **Deck inspection** — detect NPS, MODE, SDEF, F tallies, GEB, energy cards
- **Workflow planning** — structured plan generation from inspection + user intent
- **NPS-only deck patching** — change NPS without touching source

### Fixed
- Consistent MISSING_MCNP_OUTPUT error handling across run/sweep commands
- Structured error protocol (code + message dicts) applied across all workflow paths

---

## [0.1.0] — 2026-05-12

### Added
- Initial migration from `legacy/auto.py`
- MCNP input generation (distance, reference point, NPS, energy, composite source, GEB)
- MPI batch dry-run planning and confirmed execution
- F8 tally CSV extraction
- Spectra plotting with linear/log comparison
- GEB analysis and SPE-based GEB fitting
- Origin OPJ export
- Batch run with manifest validation
- ASCII-safe JSON CLI
