"""Built-in MCNP model registry with canonical reference points.

Entries may be *verified* or *template*.  Every entry defines named
reference points (aluminum_shell_front, nai_crystal_center,
nai_crystal_front_surface) with explicit positions, basis, and
verification status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# reference-point alias tables
# ---------------------------------------------------------------------------

REFERENCE_POINT_ALIASES: dict[str, str] = {
    # ── aluminum_shell_front ──
    "aluminum_shell_front": "aluminum_shell_front",
    "aluminum_shell": "aluminum_shell_front",
    "al_shell_front": "aluminum_shell_front",
    "al_shell": "aluminum_shell_front",
    "aluminum_front": "aluminum_shell_front",
    "housing_front": "aluminum_shell_front",
    "detector_window_outer": "aluminum_shell_front",
    "铝壳表面": "aluminum_shell_front",
    "铝壳前表面": "aluminum_shell_front",
    "外壳表面": "aluminum_shell_front",
    "探测器外壳表面": "aluminum_shell_front",
    "铝窗表面": "aluminum_shell_front",
    # ── nai_crystal_center ──
    "nai_crystal_center": "nai_crystal_center",
    "crystal_center": "nai_crystal_center",
    "nai_center": "nai_crystal_center",
    "scintillator_center": "nai_crystal_center",
    "碘化钠晶体中心": "nai_crystal_center",
    "NaI晶体中心": "nai_crystal_center",
    "晶体中心": "nai_crystal_center",
    "探测器晶体中心": "nai_crystal_center",
    # ── nai_crystal_front_surface ──
    "nai_crystal_front_surface": "nai_crystal_front_surface",
    "crystal_front": "nai_crystal_front_surface",
    "crystal_front_surface": "nai_crystal_front_surface",
    "nai_front_surface": "nai_crystal_front_surface",
    "scintillator_front": "nai_crystal_front_surface",
    "碘化钠晶体前端表面": "nai_crystal_front_surface",
    "碘化钠晶体前表面": "nai_crystal_front_surface",
    "NaI晶体前表面": "nai_crystal_front_surface",
    "晶体前端表面": "nai_crystal_front_surface",
    "晶体前表面": "nai_crystal_front_surface",
}

AMBIGUOUS_ALIASES: set[str] = {
    "crystal_surface",
    "nai_surface",
    "晶体表面",
    "NaI晶体表面",
    "碘化钠晶体表面",
}

CANONICAL_NAMES_ZH: dict[str, str] = {
    "aluminum_shell_front": "铝壳前表面",
    "nai_crystal_center": "碘化钠晶体中心",
    "nai_crystal_front_surface": "碘化钠晶体前端表面",
}

# ---------------------------------------------------------------------------
# model registry
# ---------------------------------------------------------------------------

MODEL_ENTRIES: dict[str, dict[str, Any]] = {
    "nai_3x3_verified": {
        "id": "nai_3x3_verified",
        "display_name": "3x3 NaI(Tl) verified deck",
        "verified": True,
        "status": "verified",
        "source": "A.txt — encapsulated Am-241 disk source, TR1 translated, F8 pulse-height tally on crystal cell 104",
        "deck_path": str(_FIXTURES / "nai_3x3_verified.txt"),
        "reference_points": {
            "nai_crystal_front_surface": {
                "position": [0.0, 0.0, 0.0],
                "basis": "derived_from_A_txt_surface_14_pz_0",
                "verified": True,
            },
            "nai_crystal_center": {
                "position": [0.0, 0.0, 3.81],
                "basis": "derived_from_A_txt_crystal_z_range_0_to_7.62",
                "verified": True,
            },
            "aluminum_shell_front": {
                "position": [0.0, 0.0, -0.34],
                "basis": "derived_from_A_txt_surface_11_pz_minus_0.340",
                "verified": True,
            },
        },
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
        "reference_points": {
            "nai_crystal_front_surface": {
                "position": [0.0, 0.0, 0.0],
                "basis": "template_coordinate_convention",
                "verified": False,
                "requires_user_validation": True,
            },
            "nai_crystal_center": {
                "position": [0.0, 0.0, 1.27],
                "basis": "template_dimension_1_inch_length",
                "verified": False,
                "requires_user_validation": True,
            },
            "aluminum_shell_front": {
                "position": [0.0, 0.0, -0.1],
                "basis": "template_assumption_al_window_0.1_cm",
                "verified": False,
                "requires_user_validation": True,
            },
        },
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
        "reference_points": {
            "nai_crystal_front_surface": {
                "position": [0.0, 0.0, 0.0],
                "basis": "template_coordinate_convention",
                "verified": False,
                "requires_user_validation": True,
            },
            "nai_crystal_center": {
                "position": [0.0, 0.0, 2.54],
                "basis": "template_dimension_2_inch_length",
                "verified": False,
                "requires_user_validation": True,
            },
            "aluminum_shell_front": {
                "position": [0.0, 0.0, -0.1],
                "basis": "template_assumption_al_window_0.1_cm",
                "verified": False,
                "requires_user_validation": True,
            },
        },
    },
}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def list_models() -> list[dict[str, Any]]:
    """Return metadata for every registered built-in model."""
    return list(MODEL_ENTRIES.values())


def get_model(model_id: str) -> dict[str, Any] | None:
    """Look up a single model by id; *None* when unknown."""
    return MODEL_ENTRIES.get(model_id)


def resolve_deck_path(model_id: str) -> Path:
    """Return the absolute path to the deck file for *model_id*."""
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


def resolve_reference_point_name(
    name: str,
) -> dict[str, Any]:
    """Resolve a reference-point alias to its canonical name.

    Returns ``{"ok": True, "canonical_name": "..."}`` on success,
    or structured error on failure / ambiguity.
    """
    if name in AMBIGUOUS_ALIASES:
        return {
            "ok": False,
            "errors": [{
                "code": "AMBIGUOUS_REFERENCE_POINT",
                "message": (
                    f"'{name}' 是歧义参考面名称。"
                    "请明确选择：nai_crystal_front_surface（晶体前表面）、"
                    "nai_crystal_center（晶体中心）、"
                    "aluminum_shell_front（铝壳表面）。"
                ),
                "options": [
                    "nai_crystal_front_surface",
                    "nai_crystal_center",
                    "aluminum_shell_front",
                ],
            }],
        }
    canonical = REFERENCE_POINT_ALIASES.get(name)
    if canonical is None:
        return {
            "ok": False,
            "errors": [{
                "code": "UNKNOWN_REFERENCE_POINT",
                "message": (
                    f"未知参考面 '{name}'。"
                    f"已知参考面: {sorted(set(REFERENCE_POINT_ALIASES.values()))}"
                ),
            }],
        }
    return {"ok": True, "canonical_name": canonical}


def get_model_reference_point(
    model_id: str,
    reference_point_name: str,
) -> dict[str, Any]:
    """Resolve a named reference point for a specific model.

    Returns the full reference-point metadata including position, verified
    flag, and basis — or a structured error.
    """
    # Resolve alias first
    alias_result = resolve_reference_point_name(reference_point_name)
    if not alias_result["ok"]:
        return alias_result

    canonical = alias_result["canonical_name"]

    model = get_model(model_id)
    if model is None:
        return {
            "ok": False,
            "errors": [{
                "code": "MODEL_NOT_FOUND",
                "message": f"Unknown model '{model_id}'.",
            }],
        }

    rps = model.get("reference_points", {})
    rp = rps.get(canonical)
    if rp is None:
        return {
            "ok": False,
            "errors": [{
                "code": "REFERENCE_POINT_NOT_DEFINED_FOR_MODEL",
                "message": (
                    f"模型 '{model_id}' 未定义参考面 '{canonical}'。"
                ),
            }],
        }

    return {
        "ok": True,
        "name": reference_point_name,
        "canonical_name": canonical,
        "canonical_name_zh": CANONICAL_NAMES_ZH.get(canonical, canonical),
        "position": [float(v) for v in rp["position"]],
        "verified": rp.get("verified", False),
        "basis": rp.get("basis", "unknown"),
        "requires_user_validation": rp.get(
            "requires_user_validation",
            not rp.get("verified", False),
        ),
    }


def validate_reference_point(
    name: str, reference_points: dict | None = None
) -> dict[str, Any]:
    """Validate a reference-point name using the generator constants.

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
