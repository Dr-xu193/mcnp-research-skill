from pathlib import Path

from mcnp_research_skill.spectra.plotter import plot_spectra


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_plot_spectra_dry_run_does_not_generate_image(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "a.csv",
        "Energy (MeV),Tally (Counts/Particle)\n"
        "0.1,1\n"
        "0.2,2\n",
    )
    output_path = tmp_path / "dry_run.png"

    result = plot_spectra([str(csv_path)], str(output_path), dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["output_path"] == str(output_path)
    assert result["csv_files"] == [str(csv_path)]
    assert output_path.exists() is False


def test_plot_spectra_generates_png(tmp_path: Path) -> None:
    csv_a = write_csv(
        tmp_path / "a.csv",
        "Energy (MeV),Tally (Counts/Particle)\n"
        "0.1,1\n"
        "0.2,10\n",
    )
    csv_b = write_csv(
        tmp_path / "b.csv",
        "energy,count\n"
        "0.1,2\n"
        "0.2,20\n",
    )
    output_path = tmp_path / "compare.png"

    result = plot_spectra([str(csv_a), str(csv_b)], str(output_path))

    assert result["ok"] is True
    assert result["dry_run"] is False
    assert result["output_path"] == str(output_path)
    assert result["written_files"] == [str(output_path)]
    assert output_path.exists()
    assert output_path.stat().st_size > 0

