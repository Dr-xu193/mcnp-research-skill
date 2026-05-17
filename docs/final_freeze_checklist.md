# Final Freeze Checklist: v0.4.0-beta

Use this checklist before tagging `v0.4.0-beta`.

## Repository state

- [ ] `main` is the release branch.
- [ ] GitHub Actions is green.
- [ ] Windows matrix passes on Python 3.10, 3.11, and 3.12.
- [ ] Package smoke job builds a wheel and installs it in a clean venv.
- [ ] No local-only files such as `CLAUDE.md` are committed.

## Version and release metadata

- [ ] `pyproject.toml` version is `0.4.0b1`.
- [ ] README title says `v0.4.0-beta`.
- [ ] README test count matches the current CI count.
- [ ] `CHANGELOG.md` contains `[0.4.0-beta]`.
- [ ] `docs/release_v0.4.0_beta.md` exists.

## Packaging

- [ ] `mcnp_research_skill/models/fixtures/*.txt` is included as package data.
- [ ] `models list` works after wheel install.
- [ ] `models inspect nai_3x3_verified` works after wheel install.
- [ ] CLI entry point `mcnp-research` is declared.

## Core documentation

- [ ] `docs/ai_usage_contract.md` exists.
- [ ] `docs/error_codes.md` exists.
- [ ] `docs/real_mcnp_validation.md` exists.
- [ ] `AGENTS.md` exists.
- [ ] `.agents/skills/mcnp-research-pipeline/SKILL.md` exists.

## Model cards

- [ ] `docs/models/nai_3x3_verified.md` exists.
- [ ] `docs/models/nai_2x2_template.md` exists.
- [ ] `docs/models/nai_1x1_template.md` exists.
- [ ] `nai_3x3_verified` is documented as verified.
- [ ] `nai_1x1_template` and `nai_2x2_template` are documented as unverified templates.

## Safety and execution

- [ ] Default execution is dry-run.
- [ ] Real execution requires `--execute --confirm-user`.
- [ ] Runtime preflight reports missing MCNP and MPI separately.
- [ ] CI does not run real MCNP/MPI.
- [ ] Documentation does not provide MCNP downloads, cracks, license bypasses, or unauthorized installation instructions.

## MCNP5 behavior

- [ ] MCNP5_RSICC 1.14 diagnostics are documented.
- [ ] 80-column and encoding limitations are documented.
- [ ] `repair-deck` is documented as safe-formatting only.
- [ ] Geometry/material/tally/source physics are not silently changed.

## Workflow boundaries

- [ ] Natural-language planner remains deterministic and rule-based.
- [ ] Ambiguous reference points are not guessed silently.
- [ ] Bq/activity is not treated as NPS.
- [ ] F8 supports CSV/plot and FT8 GEB.
- [ ] Non-F8 supports run-only workflows but blocks CSV/plot and FT8 GEB.

## SPE to GEB

- [ ] SPE-derived GEB workflow is documented.
- [ ] GEB patching writes only `FT8 GEB`.
- [ ] Original deck is not overwritten.
- [ ] Poor fit quality blocks patch/run.

## Suggested final command sequence

```powershell
python -m pytest -q
python -m build --wheel
python -m venv .venv-release-smoke
.\.venv-release-smoke\Scripts\python -m pip install --upgrade pip
.\.venv-release-smoke\Scripts\python -m pip install (Get-ChildItem dist\*.whl | Select-Object -First 1).FullName
.\.venv-release-smoke\Scripts\python -m mcnp_research_skill.cli --help
.\.venv-release-smoke\Scripts\python -m mcnp_research_skill.cli --json models list
.\.venv-release-smoke\Scripts\python -m mcnp_research_skill.cli --json models inspect nai_3x3_verified
```

## Tagging

After all checks are green:

```powershell
git tag v0.4.0-beta
git push origin v0.4.0-beta
```
