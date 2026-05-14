"""MCNP input generation migrated from the legacy GUI workflow."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .constants import (
    COMPOSITE_ALIASES,
    COMPOSITE_SOURCES,
    DEFAULT_GEB_PARAMS,
    ENERGY_DICT,
    REFERENCE_POINTS,
)


def _base_result(
    *,
    dry_run: bool,
    output_dir: str,
    distance_cm: float | None,
    reference_point: str,
    z_cm: str | None,
    nps: str,
    geb_enabled: bool,
) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": dry_run,
        "generated_files": [],
        "planned_files": [],
        "metadata": {
            "distance_cm": distance_cm,
            "reference_point": reference_point,
            "reference_short": None,
            "z_cm": z_cm,
            "nps": nps,
            "geb_enabled": geb_enabled,
            "output_dir": output_dir,
        },
        "warnings": [],
        "errors": [],
    }


def _normalize_composite_sources(
    composite_sources: list[str] | None,
    aliases: dict | None = None,
) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    errors: list[str] = []
    lookup = aliases if aliases is not None else COMPOSITE_ALIASES
    for source in composite_sources or []:
        key = str(source).strip().lower().replace(" ", "")
        canonical = lookup.get(key)
        if canonical is None:
            errors.append(f"Invalid composite source: {source}")
            continue
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized, errors


def _resolve_energy_labels(
    energies: list[float] | None,
    energy_dict: dict | None = None,
) -> tuple[list[tuple[str, float]], list[str]]:
    if energy_dict is None:
        energy_dict = ENERGY_DICT
    if energies is None:
        return list(energy_dict.items()), []

    resolved: list[tuple[str, float]] = []
    errors: list[str] = []
    for energy in energies:
        try:
            value = float(energy)
        except (TypeError, ValueError):
            errors.append(f"Invalid energy value: {energy}")
            continue

        match = next(
            ((label, known) for label, known in energy_dict.items() if abs(known - value) < 1e-9),
            None,
        )
        if match is None:
            errors.append(f"Unknown single energy {energy}; use custom_energy for non-default energies")
            continue
        resolved.append(match)
    return resolved, errors


def _next_numeric_file_names(output_dir: Path, count: int, dry_run: bool) -> list[str]:
    if not output_dir.exists():
        max_n = 0
    else:
        max_n = max(
            [0]
            + [
                int(path.stem)
                for path in output_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".txt" and path.stem.isdigit()
            ]
        )
    return [f"{max_n + idx}.txt" for idx in range(1, count + 1)]


def _apply_geb(content: str, geb_enabled: bool, geb_params: dict | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    geb_pattern = r"(?i)^ft8\s+geb.*$"

    if geb_enabled:
        params = {**DEFAULT_GEB_PARAMS, **(geb_params or {})}
        a = str(params["a"]).strip()
        b = str(params["b"]).strip()
        c = str(params["c"]).strip()
        geb_str = f"FT8 GEB {a} {b} {c}"
        if re.search(geb_pattern, content, flags=re.MULTILINE):
            content = re.sub(geb_pattern, geb_str, content, flags=re.MULTILINE)
        else:
            content, n_e8 = re.subn(
                r"(?i)^(e8\s+.*)$",
                r"\1\n" + geb_str,
                content,
                flags=re.MULTILINE,
            )
            if n_e8 == 0:
                content, n_nps = re.subn(
                    r"(?i)^(nps\s+.*)$",
                    geb_str + r"\n\1",
                    content,
                    flags=re.MULTILINE,
                )
                if n_nps == 0:
                    warnings.append("GEB enabled but no e8 or nps card was found for insertion")
        return content, warnings

    content, _ = re.subn(r"(?i)^ft8\s+geb.*\n?", "", content, flags=re.MULTILINE)
    return content, warnings


def _strip_legacy_source_cards(content: str) -> str:
    content = re.sub(r"(?i)^sdef\s+.*$\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"(?i)^si\d+\s+.*$\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"(?i)^sp\d+\s+.*$\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"(?i)^tr1\s+.*$\n?", "", content, flags=re.MULTILINE)
    return content


def _inject_source(content: str, source_block: str) -> tuple[str, int]:
    return re.subn(
        r"(?i)^(f8:p,e\s+.*)$",
        source_block + r"\1",
        content,
        flags=re.MULTILINE,
    )


def _lookup_in_rps(reference_point: str, reference_points: dict) -> dict | None:
    """Try to find *reference_point* by key, short, name, or short_label field."""
    if reference_point in reference_points:
        return reference_points[reference_point]
    for _key, rp in reference_points.items():
        if (
            rp.get("short") == reference_point
            or rp.get("name") == reference_point
            or rp.get("short_label") == reference_point
        ):
            return rp
    return None


def _normalize_rp(key: str, rp: dict) -> dict:
    if "z" not in rp:
        raise ValueError(f"Reference point '{key}' is missing required field 'z'")
    try:
        z = float(rp["z"])
    except (TypeError, ValueError):
        raise ValueError(f"Reference point '{key}' has non-numeric 'z': {rp['z']!r}")
    return {"z": z, "short": str(rp.get("short", rp.get("name", key)))}


def _normalize_profile_single_energy(profile_single: dict) -> dict[str, float]:
    """Merge profile single_energy onto built-in ENERGY_DICT.

    A profile entry for a nuclide *replaces* all built-in entries for that
    nuclide.  New nuclides are added.  Raises ``ValueError`` on non-numeric
    energies.
    """
    merged = dict(ENERGY_DICT)
    for name, energies in profile_single.items():
        try:
            energies_list = list(energies)
        except TypeError:
            raise ValueError(f"Nuclide '{name}' energies must be a list, got {type(energies).__name__}")
        # Remove old entries sharing the same nuclide-name prefix
        prefix = f"{name} ("
        for old_key in [k for k in merged if k.startswith(prefix)]:
            del merged[old_key]
        for e in energies_list:
            try:
                e_float = float(e)
            except (TypeError, ValueError):
                raise ValueError(f"Nuclide '{name}' has non-numeric energy: {e!r}")
            kev = round(e_float * 1000)
            label = f"{name} ({kev} keV)"
            merged[label] = e_float
    return merged


def _normalize_profile_composite_sources(profile_composite: dict) -> tuple[dict, dict]:
    """Merge profile composite_sources onto built-in COMPOSITE_SOURCES and COMPOSITE_ALIASES.

    Raises ``ValueError`` when a required field is missing.
    """
    merged_sources = dict(COMPOSITE_SOURCES)
    merged_aliases = dict(COMPOSITE_ALIASES)

    for key, src in profile_composite.items():
        if not isinstance(src, dict):
            raise ValueError(f"Composite source '{key}' must be a mapping, got {type(src).__name__}")
        if "meta_id" not in src:
            raise ValueError(f"Composite source '{key}' is missing required field 'meta_id'")
        if "cards" not in src:
            raise ValueError(f"Composite source '{key}' is missing required field 'cards'")
        if not isinstance(src["cards"], str):
            raise ValueError(f"Composite source '{key}' 'cards' must be a string, got {type(src['cards']).__name__}")
        merged_sources[key] = {
            "meta_id": str(src["meta_id"]),
            "cards": src["cards"],
            "skip_energy_prefix": str(src.get("skip_energy_prefix", "")),
        }
        merged_aliases[key] = key
        aliases = src.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"Composite source '{key}' 'aliases' must be a list, got {type(aliases).__name__}")
        for alias in aliases:
            merged_aliases[str(alias).strip().lower().replace(" ", "")] = key
    return merged_sources, merged_aliases


def _resolve_nuclide_libraries(
    nuclides: dict | None,
) -> tuple[dict[str, float], dict, dict]:
    """Return ``(energy_dict, composite_sources, composite_aliases)``.

    When *nuclides* is ``None`` the built-in constants are returned as-is.
    """
    if nuclides is None:
        return ENERGY_DICT, COMPOSITE_SOURCES, COMPOSITE_ALIASES

    single = nuclides.get("single_energy", {})
    composite = nuclides.get("composite_sources", {})

    energy_dict = _normalize_profile_single_energy(single) if single else dict(ENERGY_DICT)
    sources_dict, aliases_dict = _normalize_profile_composite_sources(composite) if composite else (dict(COMPOSITE_SOURCES), dict(COMPOSITE_ALIASES))
    return energy_dict, sources_dict, aliases_dict


def resolve_reference_point(
    reference_point: str,
    reference_points: dict | None = None,
) -> dict:
    """Resolve a reference-point name to ``{z, short}``.

    Searches *reference_points* (usually from a profile) first, then falls
    back to the built-in ``REFERENCE_POINTS``.  Raises ``ValueError`` with
    the available keys when the name cannot be resolved.
    """
    if reference_points is not None:
        found = _lookup_in_rps(reference_point, reference_points)
        if found is not None:
            return _normalize_rp(reference_point, found)

    found = _lookup_in_rps(reference_point, REFERENCE_POINTS)
    if found is not None:
        return _normalize_rp(reference_point, found)

    available = sorted(set(REFERENCE_POINTS.keys()) | set(reference_points.keys() if reference_points else ()))
    raise ValueError(
        f"Unknown reference_point '{reference_point}'. Available: {available}"
    )


def generate_mcnp_inputs(
    base_file: str,
    output_dir: str,
    distance_cm: float,
    reference_point: str,
    nps: str,
    energies: list[float] | None = None,
    composite_sources: list[str] | None = None,
    custom_energy: float | None = None,
    geb_enabled: bool = False,
    geb_params: dict | None = None,
    dry_run: bool = False,
    reference_points: dict | None = None,
    nuclides: dict | None = None,
) -> dict[str, Any]:
    """Generate MCNP input files from a base model.

    The text transformations mirror ``MCNPPlatformApp.generate_inputs`` while
    returning structured data and supporting dry-run execution.
    """
    raw_nps = str(nps).strip().split()[0] if str(nps).strip() else ""
    result = _base_result(
        dry_run=dry_run,
        output_dir=str(output_dir),
        distance_cm=None,
        reference_point=reference_point,
        z_cm=None,
        nps=raw_nps,
        geb_enabled=geb_enabled,
    )

    if not raw_nps:
        result["errors"].append("nps must not be empty")
        return result

    try:
        energy_dict, comp_sources, comp_aliases = _resolve_nuclide_libraries(nuclides)
    except ValueError as exc:
        result["errors"].append(str(exc))
        return result

    try:
        distance = float(distance_cm)
    except (TypeError, ValueError):
        result["errors"].append(f"Invalid distance_cm: {distance_cm}")
        return result
    result["metadata"]["distance_cm"] = distance

    try:
        ref = resolve_reference_point(reference_point, reference_points)
    except ValueError as exc:
        result["errors"].append(str(exc))
        return result

    z_str = f"{(float(ref['z']) - distance):.4f}"
    result["metadata"]["z_cm"] = z_str
    result["metadata"]["reference_short"] = ref["short"]

    base_path = Path(base_file)
    if not base_path.exists():
        result["errors"].append(f"base_file does not exist: {base_file}")
        return result

    try:
        content = base_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        result["errors"].append(f"Failed to read base_file: {exc}")
        return result

    energy_items, energy_errors = _resolve_energy_labels(energies, energy_dict=energy_dict)
    composite_keys, composite_errors = _normalize_composite_sources(
        composite_sources, aliases=comp_aliases
    )
    result["errors"].extend(energy_errors)
    result["errors"].extend(composite_errors)

    if custom_energy is not None:
        try:
            custom_energy_value = float(custom_energy)
        except (TypeError, ValueError):
            result["errors"].append(f"Invalid custom_energy: {custom_energy}")
            custom_energy_value = None
    else:
        custom_energy_value = None

    if result["errors"]:
        return result

    content, n_nps = re.subn(r"(?i)^nps\s+.*$", f"nps {raw_nps}", content, flags=re.MULTILINE)
    if n_nps == 0:
        content += f"\nnps {raw_nps}\n"

    content, geb_warnings = _apply_geb(content, geb_enabled, geb_params)
    result["warnings"].extend(geb_warnings)

    content = _strip_legacy_source_cards(content)

    base_injection = (
        f"TR1 0 0 {z_str}\n"
        "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg={erg}\n"
        "si1 0 0.15\n"
        "sp1 -21 1\n"
        "{spectrum_cards}"
    )

    candidates: list[tuple[str, str]] = []
    for label, energy in energy_items:
        if "co60" in composite_keys and label.startswith("Co-60"):
            continue
        source_block = base_injection.format(erg=energy, spectrum_cards="")
        new_content, inserted = _inject_source(content, source_block)
        if inserted > 0:
            candidates.append((label, new_content))

    for key in composite_keys:
        composite = comp_sources[key]
        source_block = base_injection.format(erg="d2", spectrum_cards=composite["cards"])
        new_content, inserted = _inject_source(content, source_block)
        if inserted > 0:
            candidates.append((composite["meta_id"], new_content))

    if custom_energy_value is not None:
        source_block = base_injection.format(erg=custom_energy_value, spectrum_cards="")
        new_content, inserted = _inject_source(content, source_block)
        if inserted > 0:
            candidates.append((f"def-source({custom_energy_value * 1000:.2f}keV)", new_content))

    if not candidates:
        if not re.search(r"(?i)^f8:p,e\s+.*$", content, flags=re.MULTILINE):
            result["warnings"].append("No f8:p,e tally card found; no MCNP input files were generated")
        else:
            result["warnings"].append("No sources selected; no MCNP input files were generated")
        return result

    output_path = Path(output_dir)
    file_names = _next_numeric_file_names(output_path, len(candidates), dry_run)

    planned_entries: list[dict[str, Any]] = []
    for file_name, (meta_id, new_content) in zip(file_names, candidates):
        final_content = (
            new_content
            + f"\nc Meta_ID:{meta_id} | Dist:{distance}cm | Ref:{ref['short']}\n"
        )
        planned_entries.append(
            {
                "file_name": file_name,
                "path": str(output_path / file_name),
                "meta_id": meta_id,
                "distance_cm": distance,
                "reference_point": reference_point,
                "reference_short": ref["short"],
                "z_cm": z_str,
                "content_preview": final_content,
            }
        )

    if dry_run:
        result["ok"] = True
        result["planned_files"] = planned_entries
        return result

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        generated_files = []
        for entry in planned_entries:
            path = Path(entry["path"])
            path.write_text(entry["content_preview"], encoding="utf-8")
            generated_files.append(entry)
        result["ok"] = True
        result["generated_files"] = generated_files
        return result
    except OSError as exc:
        result["errors"].append(f"Failed to write generated input files: {exc}")
        return result
