"""Constants for GEB CSV analysis."""

from __future__ import annotations

M_E_C2 = 0.511

SP2_WEIGHTS: dict[str, dict[float, float]] = {
    "CO-60": {1.173: 0.9985, 1.332: 0.9998},
    "CS-137": {0.662: 0.851},
    "NA-22": {0.511: 1.798, 1.274: 0.9994},
    "BA-133": {
        0.081: 0.329,
        0.276: 0.071,
        0.303: 0.183,
        0.356: 0.6205,
        0.384: 0.089,
    },
    "AM-241": {0.0595: 0.359},
}

GEB_PRESETS: dict[str, tuple[float, float, float]] = {
    "high_precision_wide_energy": (-0.00789, 0.06769, 0.21159),
    "standard_general": (0.0, 0.061, 0.0),
    "high_quality_crystal": (0.0, 0.055, 0.0),
    "aged_crystal": (0.01, 0.07, 0.0),
}

DEFAULT_REFERENCE_PARAMS: dict[str, float] = {
    "A": -0.00789,
    "B": 0.06769,
    "C": 0.21159,
}

SPE_CALIBRATIONS: dict[str, dict[str, float]] = {
    "4-29": {"a": -118.408, "b": 2.279, "c": -0.000349306},
    "4-30": {"a": -16.2993, "b": 1.8952, "c": 6.08347e-05},
}

NUCLIDE_ENERGIES: dict[str, list[float]] = {
    "CO-60": [1.173, 1.332],
    "CS-137": [0.662],
    "NA-22": [0.511, 1.274],
    "BA-133": [0.081, 0.276, 0.303, 0.356, 0.384],
    "AM-241": [0.0595],
}
