from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "AGENTS.md"
SKILL_PATH = ROOT / ".agents" / "skills" / "mcnp-research-pipeline" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_agents_md_exists_and_contains_safety_rules() -> None:
    assert AGENTS_PATH.exists()
    text = _read(AGENTS_PATH)

    for required in [
        "legacy/auto.py",
        "dry_run",
        "--execute --confirm-mpi",
        "--execute --confirm-origin",
        "ASCII-safe JSON",
        "pytest",
        "tkinter",
        "messagebox",
        "print",
    ]:
        assert required in text


def test_skill_md_exists_with_required_frontmatter() -> None:
    assert SKILL_PATH.exists()
    text = _read(SKILL_PATH)

    assert text.startswith("---\n")
    assert "name: mcnp-research-pipeline" in text
    assert "description: Use this skill for MCNP5 efficiency calibration workflows" in text


def test_skill_md_contains_workflow_and_high_risk_rules() -> None:
    text = _read(SKILL_PATH)

    for required in [
        "When to use",
        "Available capabilities",
        "Preferred workflow",
        "High-risk operations",
        "What not to do",
        "Expected outputs",
        "Troubleshooting",
        "dry_run",
        "confirm-mpi",
        "confirm-origin",
        "legacy/auto.py",
        "pytest",
    ]:
        assert required in text
