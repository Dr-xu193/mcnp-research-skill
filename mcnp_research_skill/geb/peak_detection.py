"""Filename-based GEB peak range inference."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def infer_peak_ranges_from_filename(filename: str) -> dict[str, Any]:
    """Infer expected peak search windows from a CSV filename."""
    peaks: list[float] = []
    fn = Path(filename).name.lower()
    warnings: list[str] = []

    if "composite" in fn:
        if "na-22" in fn or "na22" in fn:
            peaks = [0.511, 1.274]
        elif "co-60" in fn or "co60" in fn:
            peaks = [1.173, 1.332]
        elif "ba-133" in fn or "ba133" in fn:
            peaks = [0.081, 0.276, 0.303, 0.356, 0.384]
    else:
        kev_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*kev", fn)
        if kev_match:
            peaks.append(float(kev_match.group(1)) / 1000.0)
        else:
            mev_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*mev", fn)
            if mev_match:
                peaks.append(float(mev_match.group(1)))
            elif "cs-137" in fn or "cs137" in fn:
                peaks.append(0.662)
            elif "am-241" in fn or "am241" in fn:
                peaks.append(0.0595)

    if not peaks:
        peaks = []
        ranges = [(0.1, 3.0)]
        warnings.append("No known peak metadata found in filename; using broad default range")
    else:
        ranges = []
        for energy in peaks:
            window = max(0.05, energy * 0.06)
            ranges.append((round(max(0.01, energy - window), 3), round(energy + window, 3)))

    return {
        "ok": True,
        "filename": filename,
        "peaks": peaks,
        "ranges": ranges,
        "warnings": warnings,
        "errors": [],
    }

