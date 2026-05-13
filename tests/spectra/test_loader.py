from pathlib import Path

import pytest

from mcnp_research_skill.spectra.loader import load_spectrum_csv


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_spectrum_csv_uses_standard_energy_and_tally_columns(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "Cs-137_20cm_Data.csv",
        "Energy (MeV),Tally (Counts/Particle),Relative Error\n"
        "0.1,2.0,0.01\n"
        "0.2,4.0,0.02\n",
    )

    result = load_spectrum_csv(str(csv_path))

    assert result["ok"] is True
    assert result["label"] == "Cs-137_20cm"
    assert result["x_column"] == "Energy (MeV)"
    assert result["y_column"] == "Tally (Counts/Particle)"
    assert result["energy"] == [0.1, 0.2]
    assert result["tally"] == [2.0, 4.0]


def test_load_spectrum_csv_uses_lowercase_energy_and_count_columns(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "lowercase.csv",
        "energy,count\n"
        "0.3,5\n"
        "0.4,6\n",
    )

    result = load_spectrum_csv(str(csv_path))

    assert result["ok"] is True
    assert result["x_column"] == "energy"
    assert result["y_column"] == "count"
    assert result["energy"] == [0.3, 0.4]
    assert result["tally"] == [5, 6]


def test_load_spectrum_csv_falls_back_to_first_two_columns(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "fallback.csv",
        "bin,value,error\n"
        "1,10,0.1\n"
        "2,20,0.2\n",
    )

    result = load_spectrum_csv(str(csv_path))

    assert result["ok"] is True
    assert result["x_column"] == "bin"
    assert result["y_column"] == "value"
    assert result["energy"] == [1, 2]
    assert result["tally"] == [10, 20]


def test_load_spectrum_csv_requires_at_least_two_columns(tmp_path: Path) -> None:
    csv_path = write_csv(tmp_path / "bad.csv", "energy\n0.1\n")

    with pytest.raises(ValueError):
        load_spectrum_csv(str(csv_path))

