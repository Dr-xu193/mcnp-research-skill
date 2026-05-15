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

_SUPPORTED_STRATEGIES = {"preserve_existing_source", "point_sdef_pos", "disk_tr1"}


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


def _used_card_ids(lines: list[str]) -> set[int]:
    """Return set of card IDs used by existing TR/SI/SP."""
    ids: set[int] = set()
    for line in lines:
        if _is_comment_line(line):
            continue
        for pat in (_TR_CARD_RE, _SI_RE, _SP_RE):
            m = pat.match(line)
            if m:
                # extract the numeric suffix
                raw = line.strip().split()[0].lower()
                for prefix in ("tr", "si", "sp"):
                    if raw.startswith(prefix):
                        try:
                            ids.add(int(raw[len(prefix):]))
                        except ValueError:
                            pass
    return ids


def _auto_card_id(lines: list[str]) -> int:
    """Return the smallest positive integer not used by TR/SI/SP."""
    used = _used_card_ids(lines)
    n = 1
    while n in used:
        n += 1
    return n


def _validate_disk_tr1_params(
    source_position, source_energy, source_radius, source_ext, source_particle, source_card_id, lines
) -> tuple[list[dict], dict | None]:
    """Validate disk_tr1 params. Returns (errors, resolved_params)."""
    errors: list[dict] = []
    resolved: dict = {"pos": None, "energy": None, "radius": None, "ext": 0, "pcode": 2, "cid": None}

    # position
    if source_position is None:
        errors.append({"code": "MISSING_SOURCE_POSITION", "message": "source_position is required for disk_tr1"})
    else:
        try:
            resolved["pos"] = [float(v) for v in source_position]
            if len(resolved["pos"]) != 3:
                errors.append({"code": "INVALID_SOURCE_POSITION", "message": f"source_position must have 3 values, got {len(resolved['pos'])}"})
        except (TypeError, ValueError):
            errors.append({"code": "INVALID_SOURCE_POSITION", "message": f"source_position must be numeric: {source_position!r}"})

    # energy
    if source_energy is None:
        errors.append({"code": "MISSING_SOURCE_ENERGY", "message": "source_energy is required for disk_tr1"})
    else:
        try:
            resolved["energy"] = float(source_energy)
            if resolved["energy"] <= 0:
                errors.append({"code": "INVALID_SOURCE_ENERGY", "message": f"source_energy must be positive, got {resolved['energy']}"})
        except (TypeError, ValueError):
            errors.append({"code": "INVALID_SOURCE_ENERGY", "message": f"source_energy must be numeric: {source_energy!r}"})

    # radius
    if source_radius is None:
        errors.append({"code": "MISSING_SOURCE_RADIUS", "message": "source_radius is required for disk_tr1"})
    else:
        try:
            resolved["radius"] = float(source_radius)
            if resolved["radius"] <= 0:
                errors.append({"code": "INVALID_SOURCE_RADIUS", "message": f"source_radius must be positive, got {resolved['radius']}"})
        except (TypeError, ValueError):
            errors.append({"code": "INVALID_SOURCE_RADIUS", "message": f"source_radius must be numeric: {source_radius!r}"})

    # ext
    try:
        resolved["ext"] = float(source_ext) if source_ext is not None else 0
    except (TypeError, ValueError):
        errors.append({"code": "INVALID_SOURCE_EXT", "message": f"source_ext must be numeric: {source_ext!r}"})

    # particle
    if source_particle is not None:
        sp = str(source_particle).strip().lower()
        if sp in ("p", "photon", "2"):
            resolved["pcode"] = 2
        else:
            errors.append({"code": "INVALID_SOURCE_PARTICLE", "message": f"source_particle must be p/photon/2, got {source_particle!r}"})

    # card ID
    if source_card_id is not None:
        try:
            cid = int(source_card_id)
            if cid <= 0:
                errors.append({"code": "INVALID_SOURCE_CARD_ID", "message": f"source_card_id must be positive, got {cid}"})
            else:
                used = _used_card_ids(lines)
                if cid in used:
                    errors.append({"code": "SOURCE_CARD_ID_CONFLICT", "message": f"source_card_id {cid} is already used by TR/SI/SP; choose another"})
                resolved["cid"] = cid
        except (TypeError, ValueError):
            errors.append({"code": "INVALID_SOURCE_CARD_ID", "message": f"source_card_id must be an integer: {source_card_id!r}"})
    else:
        resolved["cid"] = _auto_card_id(lines)

    return errors, resolved


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
    source_radius: float | str | None = None,
    source_ext: float | str | None = 0,
    source_card_id: int | str | None = None,
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

    # ---- disk_tr1 ----
    if source_strategy == "disk_tr1":
        errs, params = _validate_disk_tr1_params(
            source_position, source_energy, source_radius, source_ext, source_particle, source_card_id, lines,
        )
        if errs:
            all_errors.extend(errs)

        sdef_indices = [i for i, l in enumerate(lines) if not _is_comment_line(l) and _SDEF_RE.match(l)]
        if len(sdef_indices) > 1:
            all_errors.append({"code": "MULTIPLE_SDEF", "message": f"Multiple SDEF cards found at lines {[i+1 for i in sdef_indices]}; refusing to patch."})
        if all_errors:
            return _build_result(False, False, [], text, warnings=all_warnings, errors=all_errors)

        cid = params["cid"]
        pos = params["pos"]
        rad = params["radius"]
        ext = params["ext"]
        erg = params["energy"]
        pc = params["pcode"]

        tr_line = f"tr{cid} {_format_pos_value(pos[0])} {_format_pos_value(pos[1])} {_format_pos_value(pos[2])}"
        sdef_line = f"sdef pos=0 0 0 rad=d{cid} ext={_format_pos_value(ext)} par={pc} tr={cid} erg={_format_erg_value(erg)}"
        si_line = f"si{cid} 0 {_format_pos_value(rad)}"
        sp_line = f"sp{cid} -21 1"

        old_sdef_raw = None
        if sdef_indices:
            idx = sdef_indices[0]
            m = _SDEF_RE.match(lines[idx])
            old_sdef_raw = m.group(1) if m else ""
            old_line = lines[idx].rstrip("\n\r")
            lines[idx] = sdef_line + "\n"
            # Insert TR/SI/SP after SDEF
            lines.insert(idx + 1, sp_line + "\n")
            lines.insert(idx + 1, si_line + "\n")
            lines.insert(idx + 1, tr_line + "\n")
            all_patches.append({"kind": "sdef", "action": "replace", "old": old_line.strip(), "new": sdef_line, "line_number": idx + 1})
            all_patches.append({"kind": "tr", "action": "insert", "card": f"tr{cid}"})
            all_patches.append({"kind": "si_sp", "action": "insert", "card": f"si{cid}/sp{cid}"})
        else:
            # Insert before NPS if found, else append
            nps_idxs = [i for i, l in enumerate(lines) if not _is_comment_line(l) and _NPS_RE.match(l)]
            insert_at = nps_idxs[0] if nps_idxs else len(lines)
            new_cards = [tr_line + "\n", sdef_line + "\n", si_line + "\n", sp_line + "\n"]
            for card in reversed(new_cards):
                lines.insert(insert_at, card)
            all_patches.append({"kind": "disk_tr1", "action": "insert", "card_id": cid})
        any_changed = True
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
    source_radius: float | str | None = None,
    source_ext: float | str | None = 0,
    source_card_id: int | str | None = None,
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
                        source_particle=source_particle, source_radius=source_radius,
                        source_ext=source_ext, source_card_id=source_card_id)
    if not result["ok"]:
        return result
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result["text"], encoding="utf-8")
    except OSError as exc:
        result["ok"] = False; result["errors"].append(str(exc)); result["changed"] = False
    result["input_path"] = str(in_path); result["output_path"] = str(out_path)
    return result


# ===================================================================
# GEB patching
# ===================================================================

_FT8_RE = re.compile(r"^[fF][tT]8\s+[gG][eE][bB]\s+", re.IGNORECASE)
_F8_RE = re.compile(r"^[fF]8\s*:", re.IGNORECASE)


def patch_geb(
    text: str,
    A: float,
    B: float,
    C: float,
    tally_id: int = 8,
) -> dict[str, Any]:
    """Write or replace FT8 GEB card in *text*. Only applies to F8 tally decks."""
    lines = text.split("\n")
    f8_exists = any(_F8_RE.match(l.strip()) for l in lines if l.strip())
    if not f8_exists:
        return {
            "ok": False, "changed": False, "text": text,
            "errors": [{"code": "GEB_REQUIRES_F8",
                "message": "GEB only applies to F8 pulse-height tally."}],
            "warnings": [], "patches": [],
        }

    ft8_card = f"FT{tally_id} GEB {A:.5f} {B:.5f} {C:.5f}"
    changed = False
    patches: list[dict] = []
    warnings: list[str] = []

    ft8_indices = [i for i, l in enumerate(lines) if _FT8_RE.match(l.strip())]
    if ft8_indices:
        idx = ft8_indices[0]
        old_line = lines[idx].rstrip("\n")
        lines[idx] = ft8_card
        changed = True
        patches.append({"kind": "ft8_geb", "action": "replace", "line": idx + 1,
                        "before": old_line.strip(), "after": ft8_card})
        if len(ft8_indices) > 1:
            warnings.append(f"Multiple FT8 GEB cards; only first replaced.")
    else:
        f8_idx = next((i for i, l in enumerate(lines) if _F8_RE.match(l.strip())), None)
        if f8_idx is not None:
            lines.insert(f8_idx + 1, ft8_card)
            changed = True
            patches.append({"kind": "ft8_geb", "action": "insert", "line": f8_idx + 2,
                            "after": ft8_card})
        else:
            return {
                "ok": False, "changed": False, "text": text,
                "errors": [{"code": "GEB_PATCH_FAILED",
                    "message": "Cannot locate F8 tally line to insert FT8 GEB."}],
                "warnings": [], "patches": [],
            }

    return {
        "ok": True, "changed": changed, "text": "\n".join(lines),
        "errors": [], "warnings": warnings, "patches": patches,
    }
