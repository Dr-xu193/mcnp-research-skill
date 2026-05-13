import csv
from pathlib import Path

from mcnp_research_skill.mcnp_output.tally_extractor import extract_tally_csvs


def write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def minimal_mcnp_output() -> str:
    return (
        "header\n"
        "     energy\n"
        "  0.100  1.250E-03  0.01\n"
        "  0.200  2.500E-03  0.02\n"
        " total  3.750E-03  0.03\n"
    )


def test_extract_tally_csvs_extracts_three_columns_from_minimal_output(tmp_path: Path) -> None:
    write_text(tmp_path / "Cs137-result.txt", minimal_mcnp_output())

    result = extract_tally_csvs(str(tmp_path), dry_run=True)

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["planned_files"][0]["row_count"] == 2
    assert result["planned_files"][0]["rows"] == [
        [0.1, 1.25e-03, 0.01],
        [0.2, 2.5e-03, 0.02],
    ]


def test_extract_tally_csvs_generates_data_csv_with_utf8_sig(tmp_path: Path) -> None:
    write_text(tmp_path / "sample.txt", minimal_mcnp_output())

    result = extract_tally_csvs(str(tmp_path), dry_run=False)
    csv_path = tmp_path / "sample_Data.csv"

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["csv_files"] == [str(csv_path)]
    assert csv_path.exists()
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["Energy (MeV)", "Tally (Counts/Particle)", "Relative Error"]
    assert rows[1] == ["0.1", "0.00125", "0.01"]


def test_extract_tally_csvs_dry_run_does_not_write_csv(tmp_path: Path) -> None:
    write_text(tmp_path / "sample.txt", minimal_mcnp_output())

    result = extract_tally_csvs(str(tmp_path), dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["planned_files"][0]["csv_path"] == str(tmp_path / "sample_Data.csv")
    assert not (tmp_path / "sample_Data.csv").exists()


def test_extract_tally_csvs_skips_numeric_input_files(tmp_path: Path) -> None:
    write_text(tmp_path / "1.txt", minimal_mcnp_output())
    write_text(tmp_path / "result.txt", minimal_mcnp_output())

    result = extract_tally_csvs(str(tmp_path), dry_run=True)

    assert result["count"] == 1
    assert result["processed_files"] == [str(tmp_path / "result.txt")]


def test_extract_tally_csvs_skips_transient_and_base_files(tmp_path: Path) -> None:
    for name in ["i.txt", "o.txt", "b.txt"]:
        write_text(tmp_path / name, minimal_mcnp_output())
    write_text(tmp_path / "final.txt", minimal_mcnp_output())

    result = extract_tally_csvs(str(tmp_path), dry_run=True)

    assert result["count"] == 1
    assert result["processed_files"] == [str(tmp_path / "final.txt")]


def test_extract_tally_csvs_warns_when_energy_marker_missing(tmp_path: Path) -> None:
    write_text(tmp_path / "no-energy.txt", "header\n0.1 1 0.1\n")

    result = extract_tally_csvs(str(tmp_path), dry_run=True)

    assert result["ok"] is False
    assert result["count"] == 0
    assert any("energy" in warning.lower() for warning in result["warnings"])


def test_extract_tally_csvs_returns_error_when_target_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = extract_tally_csvs(str(missing), dry_run=True)

    assert result["ok"] is False
    assert result["errors"]
    assert result["count"] == 0

