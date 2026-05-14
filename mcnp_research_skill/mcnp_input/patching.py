"""Minimal deterministic MCNP deck patching.

Phase 3C — only NPS replacement and ``preserve_existing_source`` are
supported.  No source cards, geometry, materials, or tally cards are
modified.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_NPS_RE = re.compile(r"(?i)^(nps\s+)(\S+)(.*)$")

_SUPPORTED_STRATEGIES = {"preserve_existing_source"}


def _is_comment_line(line: str) -> bool:
    stripped = line.lstrip()
    return bool(stripped) and stripped[0].lower() in ("c",)


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
    """Parse an NPS value string, supporting scientific notation."""
    token = raw.strip()
    if not token:
        return None
    token_lower = token.lower().replace("d", "e")
    try:
        return float(token_lower)
    except ValueError:
        return None


def patch_deck(
    text: str,
    *,
    nps: str | int | float | None = None,
    source_strategy: str = "preserve_existing_source",
) -> dict[str, Any]:
    """Apply deterministic patches to *text*.

    Currently only NPS patching is supported.  When *nps* is ``None`` the
    deck is returned unchanged with ``changed=false`` and ``ok=true``.
    """
    # ---- source_strategy ----
    if source_strategy not in _SUPPORTED_STRATEGIES:
        return _build_result(
            False,
            False,
            [],
            text,
            errors=[
                {
                    "code": "UNSUPPORTED_SOURCE_STRATEGY",
                    "message": (
                        f"source_strategy '{source_strategy}' is not supported; "
                        f"currently only {sorted(_SUPPORTED_STRATEGIES)} is available"
                    ),
                }
            ],
        )

    # ---- no-op ----
    if nps is None:
        return _build_result(True, False, [], text)

    # ---- parse NPS ----
    if isinstance(nps, (int, float)):
        nps_float = float(nps)
    else:
        nps_float_val = _parse_nps(str(nps))
        if nps_float_val is None:
            return _build_result(
                False, False, [], text,
                errors=[{"code": "INVALID_NPS", "message": f"Cannot parse NPS value: {nps!r}"}],
            )
        nps_float = nps_float_val

    if nps_float <= 0:
        return _build_result(
            False, False, [], text,
            errors=[{"code": "INVALID_NPS", "message": f"NPS must be positive, got {nps_float}"}],
        )

    nps_str = _normalise_nps_str(nps_float)

    # ---- find NPS cards (exclude comment lines) ----
    lines = text.splitlines(keepends=True)
    nps_indices: list[int] = []
    for i, line in enumerate(lines):
        if _is_comment_line(line):
            continue
        if _NPS_RE.match(line):
            nps_indices.append(i)

    # ---- multiple NPS → reject ----
    if len(nps_indices) > 1:
        return _build_result(
            False, False, [], text,
            errors=[
                {
                    "code": "MULTIPLE_NPS",
                    "message": f"Multiple NPS cards found at lines {[i + 1 for i in nps_indices]}; refusing to patch automatically.",
                }
            ],
        )

    # ---- single NPS → replace ----
    if len(nps_indices) == 1:
        idx = nps_indices[0]
        old_line = lines[idx].rstrip("\n\r")
        m = _NPS_RE.match(lines[idx])
        old_value = m.group(2) if m else ""
        after = m.group(3) if m else ""
        lines[idx] = f"nps {nps_str}{after}\n"
        patches = [
            {
                "kind": "nps",
                "action": "replace",
                "old": old_line.strip(),
                "new": lines[idx].strip(),
                "line_number": idx + 1,
                "value": nps_float,
            }
        ]
        return _build_result(True, True, patches, "".join(lines))

    # ---- no NPS → append ----
    text_out = text.rstrip("\n") + f"\nnps {nps_str}\n"
    patches = [
        {
            "kind": "nps",
            "action": "append",
            "line_number": len(lines) + 1,
            "value": nps_float,
        }
    ]
    return _build_result(True, True, patches, text_out)


def patch_deck_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    nps: str | int | float | None = None,
    source_strategy: str = "preserve_existing_source",
) -> dict[str, Any]:
    """Read *input_path*, patch, and write *output_path*.

    On failure the output file is **not** written.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)

    if not in_path.exists():
        return {
            "ok": False,
            "changed": False,
            "patches": [],
            "warnings": [],
            "errors": [f"File does not exist: {input_path}"],
        }

    try:
        text = in_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {
            "ok": False,
            "changed": False,
            "patches": [],
            "warnings": [],
            "errors": [str(exc)],
        }

    result = patch_deck(text, nps=nps, source_strategy=source_strategy)

    if not result["ok"]:
        return result

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result["text"], encoding="utf-8")
    except OSError as exc:
        result["ok"] = False
        result["errors"].append(str(exc))
        result["changed"] = False

    result["input_path"] = str(in_path)
    result["output_path"] = str(out_path)
    return result
