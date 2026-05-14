"""Built-in MCNP model registry.

Entries may be *verified* (``verified=True`` — real detector, known
geometry, validated MCNP output) or *template* (``verified=False``,
``status="template"`` — simplified starter deck for user calibration).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

MODEL_ENTRIES: dict[str, dict[str, Any]] = {
    "nai_3x3_verified": {
        "id": "nai_3x3_verified",
        "display_name": "3x3 NaI(Tl) verified deck",
        "verified": True,
        "status": "verified",
        "source": "A.txt — encapsulated Am-241 disk source, TR1 translated, F8 pulse-height tally on crystal cell 104",
        "deck_path": str(_FIXTURES / "nai_3x3_verified.txt"),
    },
    "nai_1x1_template": {
        "id": "nai_1x1_template",
        "display_name": "1x1 NaI(Tl) unverified template",
        "verified": False,
        "status": "template",
        "template": True,
        "requires_user_validation": True,
        "source": "Saint-Gobain / vendor datasheet nominal dimensions (1\" dia x 1\" length)",
        "basis": (
            "Crystal: NaI(Tl) 3.67 g/cm3 from A.txt fixture m1. "
            "Al housing from A.txt fixture m3. "
            "Air from A.txt fixture m6. "
            "1 inch = 2.54 cm; radius = 1.27 cm."
        ),
        "assumptions": [
            "Al housing wall thickness 0.1 cm (1 mm) — user MUST validate",
            "Al front window thickness 0.1 cm (1 mm) — user MUST validate",
            "No PMT / reflector / optical window / rear structure",
            "z=0 plane is a template coordinate convention, not a measured surface",
        ],
        "notes": (
            "Simplified MCNP5 starter deck.  User must calibrate against "
            "their own detector datasheet before real analysis."
        ),
        "deck_path": str(_FIXTURES / "nai_1x1_template.txt"),
    },
    "nai_2x2_template": {
        "id": "nai_2x2_template",
        "display_name": "2x2 NaI(Tl) unverified template",
        "verified": False,
        "status": "template",
        "template": True,
        "requires_user_validation": True,
        "source": "Saint-Gobain / vendor datasheet nominal dimensions (2\" dia x 2\" length)",
        "basis": (
            "Crystal: NaI(Tl) 3.67 g/cm3 from A.txt fixture m1. "
            "Al housing from A.txt fixture m3. "
            "Air from A.txt fixture m6. "
            "1 inch = 2.54 cm; radius = 2.54 cm."
        ),
        "assumptions": [
            "Al housing wall thickness 0.1 cm (1 mm) — user MUST validate",
            "Al front window thickness 0.1 cm (1 mm) — user MUST validate",
            "No PMT / reflector / optical window / rear structure",
            "z=0 plane is a template coordinate convention, not a measured surface",
        ],
        "notes": (
            "Simplified MCNP5 starter deck.  User must calibrate against "
            "their own detector datasheet before real analysis."
        ),
        "deck_path": str(_FIXTURES / "nai_2x2_template.txt"),
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
