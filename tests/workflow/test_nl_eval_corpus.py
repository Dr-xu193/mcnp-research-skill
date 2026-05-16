from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcnp_research_skill.workflow.nl_planner import plan_request


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nl_requests.jsonl"

_MISSING_TO_CODES = {
    "source_energy": "MISSING_SOURCE_ENERGY",
    "source_radius": "MISSING_SOURCE_RADIUS",
    "distance_range": "MISSING_DISTANCE_RANGE",
    "model_or_input": "MISSING_MODEL_OR_INPUT",
}


def _cases() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def _get_path(data: dict, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_nl_eval_corpus(case: dict) -> None:
    result = plan_request(case["text"])
    expected = case.get("expected", {})

    for key, value in expected.items():
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                actual = _get_path(result, f"{key}.{subkey}")
                if isinstance(subvalue, float):
                    assert actual == pytest.approx(subvalue)
                else:
                    assert actual == subvalue
        else:
            actual = _get_path(result, key)
            if isinstance(value, float):
                assert actual == pytest.approx(value)
            else:
                assert actual == value

    expected_errors = set(case.get("expected_errors", []))
    if expected_errors:
        actual_errors = {e.get("code") for e in result.get("errors", []) if isinstance(e, dict)}
        actual_missing = set(result.get("missing_required", []))
        actual_missing_codes = {_MISSING_TO_CODES.get(item, item) for item in actual_missing}
        actual_warnings = {w.get("code") for w in result.get("warnings", []) if isinstance(w, dict)}
        combined = actual_errors | actual_missing | actual_missing_codes | actual_warnings
        assert expected_errors <= combined
