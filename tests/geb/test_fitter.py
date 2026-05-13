import pytest

from mcnp_research_skill.geb.fitter import fit_geb_parameters
from mcnp_research_skill.geb.model import evaluate_geb


def test_evaluate_geb_returns_structured_values() -> None:
    result = evaluate_geb([0.1, 0.2], A=0.01, B=0.05, C=0.2)

    assert result["ok"] is True
    assert result["values"][0] > 0
    assert result["params"] == {"A": 0.01, "B": 0.05, "C": 0.2}


def test_fit_geb_parameters_rejects_fewer_than_three_points() -> None:
    result = fit_geb_parameters([(0.662, 0.05), (1.173, 0.07)])

    assert result["ok"] is False
    assert result["fitted_params"] is None
    assert result["warnings"]


def test_fit_geb_parameters_fits_three_or_more_simulated_points() -> None:
    true_params = {"A": 0.01, "B": 0.06, "C": 0.2}
    energies = [0.081, 0.356, 0.662, 1.173, 1.332]
    pairs = [
        (energy, evaluate_geb(energy, **true_params)["value"])
        for energy in energies
    ]

    result = fit_geb_parameters(pairs)

    assert result["ok"] is True
    assert result["fitted_params"]["A"] == pytest.approx(true_params["A"], abs=1e-4)
    assert result["fitted_params"]["B"] == pytest.approx(true_params["B"], rel=1e-3)
    assert result["fitted_params"]["C"] == pytest.approx(true_params["C"], rel=1e-2)

