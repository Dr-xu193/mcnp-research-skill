"""Read-only MCNP deck preflight diagnostics.

Detects key cards (NPS, MODE, SDEF, tallies, energy bins, GEB) and
returns a structured JSON-serialisable report.  Does not modify files
and does not invoke MCNP.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# card-level regex helpers
# ---------------------------------------------------------------------------

_RE_NPS = re.compile(r"^nps\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_MODE = re.compile(r"^mode\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_F_TALLY = re.compile(r"^f(\d+)[: ](.+)$", re.IGNORECASE | re.MULTILINE)
_RE_F_MESH = re.compile(r"^fmesh(\d+)[: ](.+)$", re.IGNORECASE | re.MULTILINE)
_RE_E_CARD = re.compile(r"^e(\d+)\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_GEB = re.compile(r"^ft(\d+)\s+geb\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_SDEF = re.compile(r"^sdef\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_TR = re.compile(r"^tr(\d+)\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_SI = re.compile(r"^si(\d+)\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_RE_SP = re.compile(r"^sp(\d+)\s+(.*)$", re.IGNORECASE | re.MULTILINE)

_RE_TRCL = re.compile(r"trcl\s*=\s*(\d+)", re.IGNORECASE)


def _line_number(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def _parse_nps_value(raw: str) -> float | None:
    token = raw.strip().split()[0] if raw.strip() else ""
    if not token:
        return None
    token_lower = token.lower().replace("d", "e")
    try:
        return float(token_lower)
    except ValueError:
        return None


def _detect_tally_support(kind: str) -> bool:
    """Return True when the tally kind is currently supported for CSV / plot."""
    return kind == "F8"


def _guess_source_type(sdef_line: str | None, tr_cards: list[str]) -> str:
    """Return a short source-type guess string."""
    if sdef_line is None:
        if tr_cards:
            return "transformed_source"
        return "unknown"
    lower = sdef_line.lower()
    has_tr = bool(re.search(r"\btr\s*=", lower))
    has_rad = bool(re.search(r"\brad\s*=", lower))
    has_ext = bool(re.search(r"\bext\s*=", lower))
    has_sur = bool(re.search(r"\bsur\s*=", lower))
    has_cel = bool(re.search(r"\bcel\s*=", lower))
    has_erg = bool(re.search(r"\berg\s*=", lower))
    has_pos = bool(re.search(r"\bpos\s*=", lower))
    has_par = bool(re.search(r"\bpar\s*=", lower))

    if has_rad and has_ext and has_erg and has_par:
        return "point_like"
    if has_tr and has_pos and has_par:
        return "transformed_source"
    if has_sur:
        return "disk_or_area"
    if has_cel:
        return "cell_source"
    return "unknown"


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def inspect_deck(text: str) -> dict[str, Any]:
    """Analyse *text* (the full content of an MCNP input deck) and return a
    structured diagnostic report.
    """
    result: dict[str, Any] = {
        "ok": True,
        "title": "",
        "nps": {"present": False, "value": None, "lines": []},
        "mode": {"present": False, "particles": [], "lines": []},
        "source": {
            "has_sdef": False,
            "sdef_line": None,
            "uses_tr": [],
            "has_rad_distribution": False,
            "has_si_sp": False,
            "tr_cards": [],
            "trcl_cards": [],
            "guess": "unknown",
        },
        "tallies": [],
        "energy_cards": [],
        "geb": {"present": False, "raw": None, "lines": []},
        "warnings": [],
        "errors": [],
    }

    # --- title ---
    title_m = re.match(r"^(.+)", text)
    if title_m:
        result["title"] = title_m.group(1).strip()

    # --- NPS ---
    nps_lines: list[int] = []
    nps_values: list[float] = []
    for m in _RE_NPS.finditer(text):
        ln = _line_number(text, m.start())
        nps_lines.append(ln)
        val = _parse_nps_value(m.group(1))
        if val is not None:
            nps_values.append(val)
    if nps_lines:
        result["nps"]["present"] = True
        result["nps"]["lines"] = nps_lines
        if nps_values:
            result["nps"]["value"] = nps_values[0]
    if len(nps_lines) > 1:
        result["errors"].append(
            {
                "code": "MULTIPLE_NPS",
                "message": f"Multiple NPS cards found at lines {nps_lines}",
                "lines": nps_lines,
            }
        )
    elif len(nps_lines) == 0:
        result["warnings"].append("No NPS card found; insert NPS before execution")

    # --- MODE ---
    for m in _RE_MODE.finditer(text):
        ln = _line_number(text, m.start())
        result["mode"]["present"] = True
        result["mode"]["lines"].append(ln)
        raw_parts = m.group(1).strip().split()
        particles = [p.strip().lower().rstrip(",") for p in raw_parts if p.strip().lower() not in ("", "mode")]
        if particles:
            result["mode"]["particles"] = particles

    # --- SDEF ---
    sdef_line: int | None = None
    sdef_raw: str | None = None
    for m in _RE_SDEF.finditer(text):
        ln = _line_number(text, m.start())
        if sdef_line is None:
            sdef_line = ln
            sdef_raw = m.group(1)
    if sdef_line is not None:
        result["source"]["has_sdef"] = True
        result["source"]["sdef_line"] = sdef_line
        if sdef_raw:
            result["source"]["has_rad_distribution"] = bool(re.search(r"\brad\s*=", sdef_raw, re.IGNORECASE))
            tr_matches = re.findall(r"\btr\s*=\s*(\d+)", sdef_raw, re.IGNORECASE)
            result["source"]["uses_tr"] = list(set(tr_matches))

    # --- TR / SI / SP ---
    si_sp = False
    tr_list: list[str] = []
    for m in _RE_TR.finditer(text):
        tr_list.append(m.group(0).strip())
    for m in _RE_SI.finditer(text):
        si_sp = True
        break
    for m in _RE_SP.finditer(text):
        si_sp = True
        break
    result["source"]["has_si_sp"] = si_sp
    result["source"]["tr_cards"] = tr_list

    # --- TRCL ---
    trcl_set: set[str] = set()
    for m in _RE_TRCL.finditer(text):
        trcl_set.add(f"trcl={m.group(1)}")
    result["source"]["trcl_cards"] = sorted(trcl_set)

    # --- source guess ---
    result["source"]["guess"] = _guess_source_type(sdef_raw, tr_list)

    # --- F tallies ---
    has_f8 = False
    for m in _RE_F_TALLY.finditer(text):
        ln = _line_number(text, m.start())
        tid = int(m.group(1))
        raw = m.group(0).strip()
        kind = f"F{tid}"
        entry: dict[str, Any] = {
            "id": tid,
            "raw": raw,
            "kind": kind,
            "supported_for_csv": _detect_tally_support(kind),
            "line": ln,
        }
        if kind == "F8":
            has_f8 = True
        elif kind != "F8":
            result["warnings"].append(
                f"Detected {kind} tally, but current CSV extraction/plotting "
                "supports only F8 pulse-height tally."
            )
        if "trcl" in raw.lower():
            trcl_set.update(re.findall(r"trcl\s*=\s*(\d+)", raw, re.IGNORECASE))
        result["tallies"].append(entry)

    for m in _RE_F_MESH.finditer(text):
        ln = _line_number(text, m.start())
        tid = int(m.group(1))
        raw = m.group(0).strip()
        kind = f"FMESH{tid}"
        entry = {
            "id": tid,
            "raw": raw,
            "kind": kind,
            "supported_for_csv": False,
            "line": ln,
        }
        result["tallies"].append(entry)
        result["warnings"].append(
            f"Detected {kind} tally, but current CSV extraction/plotting "
            "supports only F8 pulse-height tally."
        )

    if not result["tallies"]:
        result["errors"].append(
            {
                "code": "NO_TALLY_CARD",
                "message": "No tally (F) card found in the deck; cannot extract CSV.",
            }
        )
    elif has_f8 and any(t["kind"] != "F8" for t in result["tallies"]):
        result["warnings"].append(
            "Multiple tally types detected; default CSV/plot will only process F8."
        )

    # --- E cards ---
    for m in _RE_E_CARD.finditer(text):
        ln = _line_number(text, m.start())
        result["energy_cards"].append(
            {
                "id": int(m.group(1)),
                "raw": m.group(0).strip(),
                "line": ln,
            }
        )

    # --- GEB ---
    for m in _RE_GEB.finditer(text):
        ln = _line_number(text, m.start())
        result["geb"]["present"] = True
        result["geb"]["raw"] = m.group(0).strip()
        result["geb"]["lines"].append(ln)

    result["ok"] = not result["errors"]
    return result


def inspect_deck_file(path: str | Path) -> dict[str, Any]:
    """Load *path* and return ``inspect_deck(text)``.

    File-not-found and read errors are returned as structured failures.
    """
    file_path = Path(path)
    if not file_path.exists():
        return {
            "ok": False,
            "path": str(file_path),
            "warnings": [],
            "errors": [f"File does not exist: {path}"],
        }
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {
            "ok": False,
            "path": str(file_path),
            "warnings": [],
            "errors": [str(exc)],
        }
    result = inspect_deck(text)
    result["path"] = str(file_path)
    return result
