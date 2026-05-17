from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_DOCS = [
    "docs/ai_usage_contract.md",
    "docs/error_codes.md",
    "docs/real_mcnp_validation.md",
    "docs/release_v0.4.0_beta.md",
    "docs/final_freeze_checklist.md",
    "docs/models/nai_3x3_verified.md",
    "docs/models/nai_2x2_template.md",
    "docs/models/nai_1x1_template.md",
    "AGENTS.md",
    ".agents/skills/mcnp-research-pipeline/SKILL.md",
]


def test_release_docs_exist() -> None:
    for rel_path in REQUIRED_DOCS:
        path = PROJECT_ROOT / rel_path
        assert path.is_file(), rel_path
        assert path.read_text(encoding="utf-8").strip(), rel_path


def test_release_notes_capture_safety_boundaries() -> None:
    text = (PROJECT_ROOT / "docs/release_v0.4.0_beta.md").read_text(encoding="utf-8")
    for expected in [
        "0.4.0b1",
        "GitHub Actions green",
        "do not run real MCNP/MPI",
        "--execute --confirm-user",
        "nai_3x3_verified",
        "nai_2x2_template",
        "SPE to GEB",
        "CSV_REQUIRES_F8",
    ]:
        assert expected in text


def test_final_freeze_checklist_covers_release_contract() -> None:
    text = (PROJECT_ROOT / "docs/final_freeze_checklist.md").read_text(encoding="utf-8")
    for expected in [
        "pyproject.toml",
        "README",
        "CHANGELOG.md",
        "package data",
        "AGENTS.md",
        "SKILL.md",
        "MCNP5_RSICC 1.14",
        "--execute --confirm-user",
        "v0.4.0-beta",
    ]:
        assert expected in text


def test_readme_links_release_hardening_docs() -> None:
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for expected in [
        "docs/models/nai_3x3_verified.md",
        "docs/models/nai_2x2_template.md",
        "docs/models/nai_1x1_template.md",
        "docs/ai_usage_contract.md",
        "docs/error_codes.md",
        "docs/real_mcnp_validation.md",
        "docs/release_v0.4.0_beta.md",
    ]:
        assert expected in text
