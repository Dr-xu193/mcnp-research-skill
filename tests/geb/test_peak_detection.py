from mcnp_research_skill.geb.peak_detection import infer_peak_ranges_from_filename


def energies(result: dict) -> list[float]:
    return result["peaks"]


def test_co60_composite_filename_infers_two_peak_ranges() -> None:
    result = infer_peak_ranges_from_filename("Co-60_Composite_Data.csv")

    assert result["ok"] is True
    assert energies(result) == [1.173, 1.332]
    assert result["ranges"] == [(1.103, 1.243), (1.252, 1.412)]


def test_na22_composite_filename_infers_two_peak_ranges() -> None:
    result = infer_peak_ranges_from_filename("Na22_composite.csv")

    assert result["ok"] is True
    assert energies(result) == [0.511, 1.274]
    assert result["ranges"] == [(0.461, 0.561), (1.198, 1.35)]


def test_ba133_composite_filename_infers_multiple_peak_ranges() -> None:
    result = infer_peak_ranges_from_filename("Ba-133_Composite_Data.csv")

    assert result["ok"] is True
    assert energies(result) == [0.081, 0.276, 0.303, 0.356, 0.384]
    assert len(result["ranges"]) == 5


def test_single_energy_cs137_filename_infers_662kev_peak_range() -> None:
    result = infer_peak_ranges_from_filename("Cs-137_20cm_Data.csv")

    assert result["ok"] is True
    assert energies(result) == [0.662]
    assert result["ranges"] == [(0.612, 0.712)]

