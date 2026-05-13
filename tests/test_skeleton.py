"""Skeleton smoke tests."""

from mcnp_research_skill import __version__
from mcnp_research_skill.origin.origin_exporter import export_origin_projects


def test_package_imports() -> None:
    assert __version__


def test_origin_exporter_dry_run_is_structured_for_missing_target() -> None:
    result = export_origin_projects("demo", dry_run=True)

    assert result["dry_run"] is True
    assert result["ok"] is False
    assert result["errors"]
