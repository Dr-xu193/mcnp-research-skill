import sys
from pathlib import Path

import pytest

from mcnp_research_skill.geb.analyzer import run_geb_csv_analysis
from mcnp_research_skill.geb.features import extract_geb_features
from mcnp_research_skill.geb.report import build_geb_report


def add_peak(rows: list[tuple[float, float]], center: float) -> None:
    rows.extend(
        [
            (round(center - 0.20, 4), 5.0),
            (round(center - 0.10, 4), 10.0),
            (round(center - 0.05, 4), 50.0),
            (round(center, 4), 100.0),
            (round(center + 0.05, 4), 50.0),
            (round(center + 0.10, 4), 10.0),
            (round(center + 0.20, 4), 5.0),
        ]
    )


def write_peak_csv(path: Path, centers: list[float]) -> Path:
    rows: list[tuple[float, float]] = []
    for center in centers:
        add_peak(rows, center)
    rows = sorted(rows)
    path.write_text(
        "Energy (MeV),Tally (Counts/Particle)\n"
        + "\n".join(f"{energy},{count}" for energy, count in rows)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_extract_geb_features_finds_peak_energy_and_fwhm(tmp_path: Path) -> None:
    csv_path = write_peak_csv(tmp_path / "Cs-137_Data.csv", [0.662])

    result = extract_geb_features(str(csv_path), (0.60, 0.72), {"A": 0, "B": 0.1, "C": 0})

    assert result["ok"] is True
    assert result["peak_E"] == pytest.approx(0.662)
    assert result["fwhm"] == pytest.approx(0.1)


def test_run_geb_csv_analysis_processes_multiple_csv_jobs(tmp_path: Path) -> None:
    co60 = write_peak_csv(tmp_path / "Co-60_Composite_Data.csv", [1.173, 1.332])
    cs137 = write_peak_csv(tmp_path / "Cs-137_Data.csv", [0.662])

    result = run_geb_csv_analysis(
        csv_jobs=[
            {"path": str(co60), "peaks": [[1.10, 1.24], [1.26, 1.40]]},
            {"path": str(cs137), "peaks": [[0.60, 0.72]]},
        ],
        reference_params={"A": 0.0, "B": 0.06, "C": 0.0},
    )

    assert result["ok"] is True
    assert len(result["detected_points"]) == 3
    assert result["fitted_params"]
    assert len(result["efficiencies"]) == 3
    assert result["report_text"]
    assert "tkinter" not in sys.modules


def test_run_geb_csv_analysis_returns_error_for_missing_csv(tmp_path: Path) -> None:
    result = run_geb_csv_analysis(
        csv_jobs=[{"path": str(tmp_path / "missing.csv"), "peaks": [[0.60, 0.72]]}],
        reference_params={"A": 0.0, "B": 0.06, "C": 0.0},
    )

    assert result["ok"] is False
    assert result["errors"]


def test_build_geb_report_returns_structured_text(tmp_path: Path) -> None:
    csv_path = write_peak_csv(tmp_path / "Cs-137_Data.csv", [0.662])
    analysis = run_geb_csv_analysis(
        csv_jobs=[
            {"path": str(csv_path), "peaks": [[0.60, 0.72], [0.60, 0.72], [0.60, 0.72]]}
        ],
        reference_params={"A": 0.0, "B": 0.06, "C": 0.0},
    )

    report = build_geb_report(analysis)

    assert "report_text" in report
    assert isinstance(report["report_text"], str)

