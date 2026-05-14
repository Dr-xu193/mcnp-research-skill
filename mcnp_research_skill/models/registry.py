"""Built-in verified MCNP model registry.

Each entry maps a stable ``model_id`` to a deck fixture shipped with the
package.  Only models that have been physically verified (real detector,
known geometry, validated MCNP output) belong here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

MODEL_ENTRIES: dict[str, dict[str, Any]] = {
    "nai_3x3_verified": {
        "id": "nai_3x3_verified",
        "display_name": "3x3 NaI(Tl) verified deck",
        "source": "A.txt — encapsulated Am-241 disk source, TR1 translated, F8 pulse-height tally on crystal cell 104",
        "deck_path": str(_FIXTURES / "nai_3x3_verified.txt"),
    },
}


def list_models() -> list[dict[str, Any]]:
    """Return metadata for every registered built-in model."""
    return list(MODEL_ENTRIES.values())


def get_model(model_id: str) -> dict[str, Any] | None:
    """Look up a single model by id; *None* when unknown."""
    return MODEL_ENTRIES.get(model_id)


def resolve_deck_path(model_id: str) -> Path:
    """Return the absolute path to the deck file for *model_id*.

    Raises ``ValueError`` when the id is not registered.
    """
    model = get_model(model_id)
    if model is None:
        available = sorted(MODEL_ENTRIES.keys())
        raise ValueError(
            f"Unknown built-in model '{model_id}'. Available: {available}"
        )
    path = Path(model["deck_path"])
    if not path.is_file():
        raise FileNotFoundError(
            f"Built-in model '{model_id}' fixture missing: {path}"
        )
    return path


def validate_reference_point(
    name: str, reference_points: dict | None = None
) -> dict[str, Any]:
    """Validate a reference-point name and return a structured result.

    Uses :func:`mcnp_research_skill.mcnp_input.generator.resolve_reference_point`
    internally.  Returns ``{"ok": True, "reference_point": {...}}`` on success,
    or ``{"ok": False, "errors": [{"code": "UNKNOWN_REFERENCE_POINT", ...}]}``
    when the name cannot be resolved.
    """
    from ..mcnp_input.generator import resolve_reference_point as _resolve

    try:
        rp = _resolve(name, reference_points)
        return {"ok": True, "reference_point": rp}
    except ValueError as exc:
        return {
            "ok": False,
            "errors": [{"code": "UNKNOWN_REFERENCE_POINT", "message": str(exc)}],
        }
