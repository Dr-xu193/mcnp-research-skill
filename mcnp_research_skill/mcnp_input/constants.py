"""Constants for MCNP input generation."""

from __future__ import annotations

ENERGY_DICT: dict[str, float] = {
    "Am-241 (59.5 keV)": 0.0595,
    "Ba-133 (81 keV)": 0.081,
    "Ba-133 (356 keV)": 0.356,
    "Cs-137 (662 keV)": 0.662,
    "Co-60 (1173 keV)": 1.173,
    "Co-60 (1332 keV)": 1.332,
}

REFERENCE_POINTS: dict[str, dict[str, float | str]] = {
    "aluminum_shell_surface": {
        "z": -0.34,
        "short": "铝壳表面",
        "legacy_label": "探测器铝壳表面 (Z = -0.34 cm)",
    },
    "crystal_front_surface": {
        "z": 0.00,
        "short": "晶体表面",
        "legacy_label": "NaI 晶体前表面 (Z = 0.00 cm)",
    },
    "crystal_center": {
        "z": 3.81,
        "short": "几何中心",
        "legacy_label": "NaI 晶体几何中心 (Z = 3.81 cm)",
    },
}

COMPOSITE_SOURCES: dict[str, dict[str, str]] = {
    "co60": {
        "meta_id": "Co-60_Composite",
        "skip_energy_prefix": "Co-60",
        "cards": "si2 L 1.1732 1.3325\nsp2 0.9985 0.9998\n",
    },
    "na22": {
        "meta_id": "Na-22_Composite",
        "skip_energy_prefix": "",
        "cards": "si2 L 0.511 1.274\nsp2 1.798 0.9994\n",
    },
    "ba133": {
        "meta_id": "Ba-133_Composite",
        "skip_energy_prefix": "",
        "cards": "si2 L 0.081 0.276 0.303 0.356 0.384\nsp2 0.329 0.071 0.183 0.6205 0.089\n",
    },
}

COMPOSITE_ALIASES: dict[str, str] = {
    "co60": "co60",
    "co-60": "co60",
    "co-60_composite": "co60",
    "co60_composite": "co60",
    "na22": "na22",
    "na-22": "na22",
    "na-22_composite": "na22",
    "na22_composite": "na22",
    "ba133": "ba133",
    "ba-133": "ba133",
    "ba-133_composite": "ba133",
    "ba133_composite": "ba133",
}

DEFAULT_GEB_PARAMS: dict[str, str] = {
    "a": "-0.00789",
    "b": "0.06769",
    "c": "0.21159",
}

GEB_PRESETS: dict[str, tuple[str, str, str]] = {
    "high_precision_wide_energy": ("-0.00789", "0.06769", "0.21159"),
    "standard_general": ("0.0", "0.061", "0.0"),
    "high_quality_crystal": ("0.0", "0.055", "0.0"),
    "aged_crystal": ("0.01", "0.07", "0.0"),
}
