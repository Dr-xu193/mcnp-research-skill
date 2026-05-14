"""Minimal deterministic MCNP deck patching.

Supports NPS replacement and two source strategies:
``preserve_existing_source`` (NPS-only) and ``point_sdef_pos``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_NPS_RE = re.compile(r"(?i)^(nps\s+)(\S+)(.*)$")
_SDEF_RE = re.compile(r"(?i)^sdef\s+(.*)$")
_SI_RE = re.compile(r"(?i)^si\d+\s+")
_SP_RE = re.compile(r"(?i)^sp\d+\s+")
_TR_CARD_RE = re.compile(r"(?i)^tr\d+\s+")

_SUPPORTED_STRATEGIES = {"preserve_existing_source", "point_sdef_pos"}


def _is_comment_line(line: str) -> bool:
    stripped = line.lstrip()
    return bool(stripped) and stripped[0].lower() in ("c",)


def _format_pos_value(v: float) -> str:
    """Format a position value, avoiding trailing .0 for whole numbers."""
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return str(v)


def _format_erg_value(v: float) -> str:
    """Format energy value without unnecessary trailing zeros."""
    s = f"{v:.9g}"
    return s


def _normalise_nps_str(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def _build_result(
    ok: bool,
    changed: bool,
    patches: list[dict],
    text: str,
    warnings: list[str] | None = None,
    errors: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "schema_version": "1.0",
        "changed": changed,
        "patches": patches,
        "text": text,
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _parse_nps(raw: str) -> float | None:
    token = raw.strip()
    if not token:
        return None
    token_lower = token.lower().replace("d", "e")
    try:
        return float(token_lower)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# _point_sdef_pos helpers
# ---------------------------------------------------------------------------


def _validate_source_params(
    source_position, source_energy, source_particle
) -> tuple[list[dict], list[float] | None, float | None, int]:
    """Validate source params. Returns (errors, pos, energy, particle_code)."""
    errors: list[dict] = []
    pos: list[float] | None = None
    energy: float | None = None
    particle_code = 2  # default photon

    # position
    if source_position is None:
        errors.append({"code": "MISSING_SOURCE_POSITION", "message": "source_position is required for point_sdef_pos"})
    else:
        try:
            pos = [float(v) for v in source_position]
        except (TypeError, ValueError):
            errors.append({"code": "INVALID_SOURCE_POSITION", "message": f"source_position must be numeric: {source_position!r}"})
        else:
            if len(pos) != 3:
                errors.append({"code": "INVALID_SOURCE_POSITION", "message": f"source_position must have exactly 3 values, got {len(pos)}"})

    # energy
    if source_energy is None:
        errors.append({"code": "MISSING_SOURCE_ENERGY", "message": "source_energy is required for point_sdef_pos"})
    else:
        try:
            energy = float(source_energy)
        except (TypeError, ValueError):
            errors.append({"code": "INVALID_SOURCE_ENERGY", "message": f"source_energy must be numeric: {source_energy!r}"})
        else:
            if energy <= 0:
                errors.append({"code": "INVALID_SOURCE_ENERGY", "message": f"source_energy must be positive, got {energy}"})

    # particle
    if source_particle is not None:
        sp = str(source_particle).strip().lower()
        if sp in ("p", "photon", "2"):
            particle_code = 2
        else:
            errors.append({"code": "INVALID_SOURCE_PARTICLE", "message": f"source_particle must be p/photon/2, got {source_particle!r}"})

    return errors, pos, energy, particle_code


def _detect_unused_source_cards(lines: list[str], old_sdef_raw: str | None) -> list[str]:
    """Return warnings if old SI/SP/TR cards or SDEF extensions may be unused."""
    warnings: list[str] = []
    has_si_sp = any(_SI_RE.match(l) or _SP_RE.match(l) for l in lines if not _is_comment_line(l))
    has_tr = any(_TR_CARD_RE.match(l) for l in lines if not _is_comment_line(l))
    has_extensions = False
    if old_sdef_raw:
        lower = old_sdef_raw.lower()
        has_extensions = any(k in lower for k in ("rad=", "ext=", "tr="))
    if has_si_sp or has_tr or has_extensions:
        warnings.append(
            "POSSIBLE_UNUSED_SOURCE_CARDS: old SDEF used rad=/ext=/tr= or "
            "SI/SP/TR cards exist; these are not removed and may be unused."
        )
    return warnings


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def patch_deck(
    text: str,
    *,
    nps: str | int | float | None = None,
    source_strategy: str = "preserve_existing_source",
    source_position: tuple[float, float, float] | list[float] | None = None,
    source_energy: float | str | None = None,
    source_particle: str | int | None = None,
) -> dict[str, Any]:
    """Apply deterministic patches to *text*."""

    # ---- source_strategy ----
    if source_strategy not in _SUPPORTED_STRATEGIES:
        return _build_result(
            False, False, [], text,
            errors=[{"code": "UNSUPPORTED_SOURCE_STRATEGY",
                     "message": f"source_strategy '{source_strategy}' is not supported; "
                                f"currently only {sorted(_SUPPORTED_STRATEGIES)} is available"}],
        )

    lines = text.splitlines(keepends=True)
    all_patches: list[dict] = []
    all_warnings: list[str] = []
    all_errors: list[dict] = []
    any_changed = False

    # ---- point_sdef_pos ----
    if source_strategy == "point_sdef_pos":
        errs, pos, energy, pcode = _validate_source_params(source_position, source_energy, source_particle)
        if errs:
            all_errors.extend(errs)

        # Find SDEF lines
        sdef_indices = [i for i, l in enumerate(lines) if not _is_comment_line(l) and _SDEF_RE.match(l)]
        if len(sdef_indices) > 1:
            all_errors.append({"code": "MULTIPLE_SDEF",
                               "message": f"Multiple SDEF cards found at lines {[i+1 for i in sdef_indices]}; refusing to patch."})
        if all_errors:
            return _build_result(False, False, [], text, warnings=all_warnings, errors=all_errors)

        sdef_line = f"sdef pos={_format_pos_value(pos[0])} {_format_pos_value(pos[1])} {_format_pos_value(pos[2])} par={pcode} erg={_format_erg_value(energy)}\n"
        old_sdef_raw = None

        if sdef_indices:
            idx = sdef_indices[0]
            m = _SDEF_RE.match(lines[idx])
            old_sdef_raw = m.group(1) if m else ""
            old_line = lines[idx].rstrip("\n\r")
            lines[idx] = sdef_line
            all_patches.append({"kind": "sdef", "action": "replace", "old": old_line.strip(),
                                "new": sdef_line.strip(), "line_number": idx + 1})
        else:
            # Insert before NPS if present, else append
            nps_idxs = [i for i, l in enumerate(lines) if not _is_comment_line(l) and _NPS_RE.match(l)]
            if nps_idxs:
                insert_at = nps_idxs[0]
                lines.insert(insert_at, sdef_line)
            else:
                lines.append(sdef_line)
            all_patches.append({"kind": "sdef", "action": "insert", "new": sdef_line.strip()})
        any_changed = True

        # Check for potentially unused cards
        all_warnings.extend(_detect_unused_source_cards(lines, old_sdef_raw))

    # ---- NPS ----
    if nps is not None:
        nps_val_str = str(nps) if isinstance(nps, str) else str(nps)
        nps_float_val = _parse_nps(nps_val_str) if isinstance(nps, str) else (float(nps) if isinstance(nps, (int, float)) else None)
        if isinstance(nps, (int, float)):
            nps_float_val = float(nps)
        elif isinstance(nps, str):
            nps_float_val = _parse_nps(nps)
        else:
            nps_float_val = None

        if nps_float_val is None:
            return _build_result(False, False, [], text, errors=[{"code": "INVALID_NPS", "message": f"Cannot parse NPS value: {nps!r}"}])
        if nps_float_val <= 0:
            return _build_result(False, False, [], text, errors=[{"code": "INVALID_NPS", "message": f"NPS must be positive, got {nps_float_val}"}])

        nps_str_val = _normalise_nps_str(nps_float_val)
        nps_idxs = [i for i, l in enumerate(lines) if not _is_comment_line(l) and _NPS_RE.match(l)]

        if len(nps_idxs) > 1:
            return _build_result(False, False, all_patches, text,
                                 warnings=all_warnings,
                                 errors=[{"code": "MULTIPLE_NPS",
                                          "message": f"Multiple NPS cards found at lines {[i+1 for i in nps_idxs]}; refusing to patch."}])

        if len(nps_idxs) == 1:
            idx = nps_idxs[0]
            old_line = lines[idx].rstrip("\n\r")
            m = _NPS_RE.match(lines[idx])
            after = m.group(3) if m else ""
            lines[idx] = f"nps {nps_str_val}{after}\n"
            all_patches.append({"kind": "nps", "action": "replace", "old": old_line.strip(),
                                "new": lines[idx].strip(), "line_number": idx + 1, "value": nps_float_val})
        else:
            text_out = "".join(lines).rstrip("\n") + f"\nnps {nps_str_val}\n"
            # Rebuild lines to incorporate the append
            lines = text_out.splitlines(keepends=True)
            all_patches.append({"kind": "nps", "action": "append", "line_number": len(lines), "value": nps_float_val})
        any_changed = True

    if all_errors:
        return _build_result(False, False, [], text, warnings=all_warnings, errors=all_errors)

    if not any_changed and nps is None and source_strategy == "preserve_existing_source":
        return _build_result(True, False, [], text)

    return _build_result(True, any_changed, all_patches, "".join(lines), warnings=all_warnings)


def patch_deck_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    nps: str | int | float | None = None,
    source_strategy: str = "preserve_existing_source",
    source_position: tuple[float, float, float] | list[float] | None = None,
    source_energy: float | str | None = None,
    source_particle: str | int | None = None,
) -> dict[str, Any]:
    """Read *input_path*, patch, and write *output_path*."""
    in_path = Path(input_path)
    out_path = Path(output_path)

    if not in_path.exists():
        return {"ok": False, "changed": False, "patches": [], "warnings": [],
                "errors": [f"File does not exist: {input_path}"]}
    try:
        text = in_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {"ok": False, "changed": False, "patches": [], "warnings": [], "errors": [str(exc)]}

    result = patch_deck(text, nps=nps, source_strategy=source_strategy,
                        source_position=source_position, source_energy=source_energy,
                        source_particle=source_particle)
    if not result["ok"]:
        return result
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result["text"], encoding="utf-8")
    except OSError as exc:
        result["ok"] = False; result["errors"].append(str(exc)); result["changed"] = False
    result["input_path"] = str(in_path); result["output_path"] = str(out_path)
    return result
