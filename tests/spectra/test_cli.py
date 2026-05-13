from pathlib import Path

from mcnp_research_skill.spectra.cli import main


def test_cli_plot_dry_run_returns_structured_result(tmp_path: Path) -> None:
    csv_path = tmp_path / "a.csv"
    csv_path.write_text(
        "Energy (MeV),Tally (Counts/Particle)\n"
        "0.1,1\n"
        "0.2,2\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "out.png"

    result = main(
        [
            "plot",
            "--csv",
            str(csv_path),
            "--output",
            str(output_path),
            "--dry-run",
        ]
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["output_path"] == str(output_path)
    assert output_path.exists() is False

