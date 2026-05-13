import pytest

from mcnp_research_skill.geb.efficiency import calculate_net_efficiency


def test_calculate_net_efficiency_returns_gross_background_and_net() -> None:
    result = calculate_net_efficiency(
        energy=[0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
        counts=[10, 20, 40, 100, 40, 20, 10],
        peak_E=1.0,
        fwhm=0.2,
        sampling_fraction=0.5,
    )

    assert result["ok"] is True
    assert result["gross_area"] == pytest.approx(240.0)
    assert result["background_area"] == pytest.approx(163.3333333333)
    assert result["net_efficiency"] == pytest.approx(153.3333333333)

