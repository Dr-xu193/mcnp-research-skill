import math
import sys
from pathlib import Path

import pytest

from mcnp_research_skill.geb.spe import (
    _merge_geb_nuclides,
    extract_fwhm_points_from_spe,
    fit_geb_from_spe_files,
    identify_nuclide_from_filename,
    parse_spe_file,
    select_spe_calibration,
)


CAL_429 = {"a": -118.408, "b": 2.279, "c": -0.000349306}


def channel_for_energy(e_mev: float, cal: dict[str, float] = CAL_429) -> int:
    e_kev = e_mev * 1000.0
    a, b, c = cal["a"], cal["b"], cal["c"]
    if c == 0:
        return int((e_kev - a) / b)
    delta = b**2 - 4 * c * (a - e_kev)
    return int((-b + math.sqrt(delta)) / (2 * c)) if delta > 0 else 512


def write_spe(path: Path, energies: list[float], *, date: str = "04/29/2026 12:00:00") -> Path:
    channels = [0] * 2048
    for energy in energies:
        center = max(10, min(len(channels) - 11, channel_for_energy(energy)))
        shape = {
            center - 6: 10,
            center - 5: 40,
            center - 4: 60,
            center - 3: 80,
            center - 2: 120,
            center - 1: 160,
            center: 200,
            center + 1: 160,
            center + 2: 120,
            center + 3: 80,
            center + 4: 60,
            center + 5: 40,
            center + 6: 10,
        }
        for ch, count in shape.items():
            channels[ch] = max(channels[ch], count)

    path.write_text(
        "$SPEC_ID:\n"
        "fixture\n"
        "$DATE_MEA:\n"
        f"{date}\n"
        "$DATA:\n"
        "0 2047\n"
        + "\n".join(str(value) for value in channels)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_parse_spe_file_reads_minimal_fixture(tmp_path: Path) -> None:
    spe_path = write_spe(tmp_path / "CS-137_4-29.spe", [0.662])

    result = parse_spe_file(str(spe_path))

    assert result["ok"] is True
    assert result["measurement_date"] == "2026-04-29T12:00:00"
    assert len(result["spectrum"]) == 2048


def test_identify_nuclide_from_filename_recognizes_supported_nuclides() -> None:
    cases = {
        "CO-60_sample.spe": "CO-60",
        "CS137_sample.spe": "CS-137",
        "NA-22_sample.spe": "NA-22",
        "BA133_sample.spe": "BA-133",
        "AM-241_sample.spe": "AM-241",
    }

    for filename, expected in cases.items():
        result = identify_nuclide_from_filename(filename)
        assert result["ok"] is True
        assert result["nuclide"] == expected


def test_select_spe_calibration_uses_429_or_430_filename() -> None:
    cal_429 = select_spe_calibration("Co-60_4-29.spe")
    cal_430 = select_spe_calibration("Co-60_4-30.spe")

    assert cal_429["ok"] is True
    assert cal_429["calibration_key"] == "4-29"
    assert cal_430["calibration_key"] == "4-30"
    assert cal_429["calibration"] != cal_430["calibration"]


def test_fit_geb_from_spe_files_rejects_fewer_than_three_valid_peaks(tmp_path: Path) -> None:
    spe_path = write_spe(tmp_path / "CS-137_4-29.spe", [0.662])

    result = fit_geb_from_spe_files([str(spe_path)])

    assert result["ok"] is False
    assert len(result["energy_fwhm_pairs"]) == 1
    assert result["warnings"]


def test_extract_fwhm_points_from_multiple_simulated_spe_files(tmp_path: Path) -> None:
    co60 = write_spe(tmp_path / "CO-60_4-29.spe", [1.173, 1.332])
    cs137 = write_spe(tmp_path / "CS-137_4-29.spe", [0.662])

    result = extract_fwhm_points_from_spe([str(co60), str(cs137)])

    assert result["ok"] is True
    assert len(result["energy_fwhm_pairs"]) >= 3
    assert {round(item["energy_mev"], 3) for item in result["energy_fwhm_pairs"]} >= {0.662, 1.173, 1.332}


def test_fit_geb_from_multiple_simulated_spe_files_returns_params(tmp_path: Path) -> None:
    co60 = write_spe(tmp_path / "CO-60_4-29.spe", [1.173, 1.332])
    cs137 = write_spe(tmp_path / "CS-137_4-29.spe", [0.662])

    result = fit_geb_from_spe_files([str(co60), str(cs137)])

    assert result["ok"] is True
    assert result["fitted_params"]
    assert set(result["fitted_params"]) == {"A", "B", "C"}


def test_unidentified_nuclide_goes_to_skipped_files(tmp_path: Path) -> None:
    unknown = write_spe(tmp_path / "UNKNOWN_4-29.spe", [0.662])

    result = extract_fwhm_points_from_spe([str(unknown)])

    assert result["ok"] is False
    assert result["skipped_files"]
    assert result["warnings"]


def test_spe_module_does_not_depend_on_gui_modules() -> None:
    assert "tkinter" not in sys.modules
    assert "tkinter.messagebox" not in sys.modules


# ---------------------------------------------------------------------------
# GEB nuclides from profile (_merge_geb_nuclides)
# ---------------------------------------------------------------------------


def test_merge_geb_default_returns_builtin():
    from mcnp_research_skill.geb.constants import NUCLIDE_ENERGIES, SP2_WEIGHTS

    energies, weights = _merge_geb_nuclides(None)
    assert energies == NUCLIDE_ENERGIES
    assert weights == SP2_WEIGHTS

    energies2, weights2 = _merge_geb_nuclides({})
    assert energies2 == NUCLIDE_ENERGIES


def test_merge_geb_adds_custom_nuclide():
    geb = {"nuclide_energies": {"TEST-100": [0.1]}}
    energies, _ = _merge_geb_nuclides(geb)
    assert "TEST-100" in energies
    assert energies["TEST-100"] == [0.1]
    # Built-in still present
    assert "CS-137" in energies


def test_merge_geb_overrides_existing_nuclide():
    geb = {"nuclide_energies": {"CS-137": [0.7, 1.0]}}
    energies, _ = _merge_geb_nuclides(geb)
    assert energies["CS-137"] == [0.7, 1.0]


def test_merge_geb_bad_energy_raises():
    geb = {"nuclide_energies": {"BAD": ["abc"]}}
    with pytest.raises(ValueError, match="BAD"):
        _merge_geb_nuclides(geb)


def test_merge_geb_sp2_weights_conversion():
    geb = {
        "nuclide_energies": {"CO-60": [1.173, 1.332]},
        "sp2_weights": {"CO-60": [0.9985, 0.9998]},
    }
    _, weights = _merge_geb_nuclides(geb)
    assert "CO-60" in weights
    assert weights["CO-60"] == {1.173: 0.9985, 1.332: 0.9998}


def test_merge_geb_sp2_weights_mismatch_raises():
    geb = {
        "nuclide_energies": {"CO-60": [1.173, 1.332]},
        "sp2_weights": {"CO-60": [0.5]},  # Only 1 weight for 2 energies
    }
    with pytest.raises(ValueError, match="sp2_weights"):
        _merge_geb_nuclides(geb)


def test_merge_geb_sp2_weights_unknown_nuclide():
    geb = {"sp2_weights": {"GHOST": [0.5]}}
    with pytest.raises(ValueError, match="GHOST"):
        _merge_geb_nuclides(geb)


def test_merge_geb_sp2_weights_bad_value():
    geb = {
        "nuclide_energies": {"CO-60": [1.173, 1.332]},
        "sp2_weights": {"CO-60": [0.5, "bad"]},
    }
    with pytest.raises(ValueError, match="CO-60"):
        _merge_geb_nuclides(geb)


def test_identify_nuclide_uses_custom_dict():
    custom = {"TEST-100": [0.1]}
    result = identify_nuclide_from_filename("test-100_4-29.spe", nuclide_energies=custom)
    assert result["ok"] is True
    assert result["nuclide"] == "TEST-100"
    assert result["energies"] == [0.1]
