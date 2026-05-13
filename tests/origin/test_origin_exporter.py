import builtins
import sys
from pathlib import Path

from mcnp_research_skill.origin.origin_exporter import _close_origin_app, export_origin_projects


def test_origin_export_dry_run_lists_csv_and_expected_opj(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample_Data.csv"
    csv_path.write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")

    result = export_origin_projects(str(tmp_path), dry_run=True)

    assert result["ok"] is True
    assert result["planned"] == [
        {
            "csv_path": str(csv_path),
            "opj_path": str(tmp_path / "sample_Data.opj"),
        }
    ]
    assert result["exported"] == []


def test_origin_export_dry_run_does_not_create_temp_workspace(tmp_path: Path) -> None:
    (tmp_path / "sample_Data.csv").write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")
    temp_workspace = tmp_path / "tmp-origin"

    result = export_origin_projects(str(tmp_path), temp_workspace=str(temp_workspace), dry_run=True)

    assert result["ok"] is True
    assert not temp_workspace.exists()


def test_origin_export_rejects_execute_without_confirmation(tmp_path: Path) -> None:
    (tmp_path / "sample_Data.csv").write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")

    result = export_origin_projects(str(tmp_path), dry_run=False, confirm=False)

    assert result["ok"] is False
    assert result["errors"]


def test_origin_export_missing_target_dir_returns_error(tmp_path: Path) -> None:
    result = export_origin_projects(str(tmp_path / "missing"), dry_run=True)

    assert result["ok"] is False
    assert result["errors"]


def test_origin_export_warns_when_no_csv_files(tmp_path: Path) -> None:
    result = export_origin_projects(str(tmp_path), dry_run=True)

    assert result["ok"] is False
    assert result["warnings"]


def test_origin_export_dry_run_does_not_import_win32com(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "sample_Data.csv").write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")
    original_import = builtins.__import__

    def guard_import(name, *args, **kwargs):  # noqa: ANN001
        if name.startswith("win32com") or name == "pythoncom":
            raise AssertionError("Origin COM modules must not be imported in dry_run")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard_import)

    result = export_origin_projects(str(tmp_path), dry_run=True)

    assert result["ok"] is True
    assert "tkinter" not in sys.modules
    assert "tkinter.messagebox" not in sys.modules


def test_origin_export_execute_reports_missing_com_dependencies(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "sample_Data.csv").write_text("Energy,Tally\n0.1,1\n", encoding="utf-8")
    original_import = builtins.__import__

    def block_origin_imports(name, *args, **kwargs):  # noqa: ANN001
        if name.startswith("win32com") or name == "pythoncom":
            raise ImportError("blocked COM import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_origin_imports)

    result = export_origin_projects(str(tmp_path), dry_run=False, confirm=True)

    assert result["ok"] is False
    assert any("COM dependencies" in error for error in result["errors"])


def test_close_origin_app_calls_callable_exit() -> None:
    class FakeOrigin:
        def __init__(self) -> None:
            self.exit_called = False

        def Exit(self) -> None:  # noqa: N802 - mirrors COM member name.
            self.exit_called = True

    fake = FakeOrigin()

    result = _close_origin_app(fake)

    assert result["ok"] is True
    assert fake.exit_called is True
    assert result["warnings"] == []


def test_close_origin_app_uses_quit_when_exit_is_bool() -> None:
    class FakeOrigin:
        Exit = True

        def __init__(self) -> None:
            self.quit_called = False

        def Quit(self) -> None:  # noqa: N802 - mirrors COM member name.
            self.quit_called = True

    fake = FakeOrigin()

    result = _close_origin_app(fake)

    assert result["ok"] is True
    assert fake.quit_called is True
    assert result["warnings"] == []


def test_close_origin_app_falls_back_to_hiding_visible() -> None:
    class FakeOrigin:
        Exit = True
        Quit = False

        def __init__(self) -> None:
            self.Visible = 1

    fake = FakeOrigin()

    result = _close_origin_app(fake)

    assert result["ok"] is True
    assert fake.Visible == 0
    assert result["warnings"] == []


def test_close_origin_app_warns_only_when_all_close_strategies_fail() -> None:
    class FakeOrigin:
        Exit = True
        Quit = False

        def __setattr__(self, name: str, value: object) -> None:
            if name == "Visible":
                raise RuntimeError("cannot hide")
            super().__setattr__(name, value)

    result = _close_origin_app(FakeOrigin())

    assert result["ok"] is False
    assert result["warnings"]
