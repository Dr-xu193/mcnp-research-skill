"""Spectrum plotting utilities migrated from the legacy SpectraEngine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .loader import load_spectrum_csv

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def plot_spectra(
    csv_files: list[str],
    output_path: str,
    mode: str = "merged",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Plot one merged linear/log comparison PNG from one or more CSV files."""
    if mode != "merged":
        raise ValueError("Only merged mode is supported in the spectra migration step")
    if not csv_files:
        raise ValueError("At least one CSV file is required")

    spectra = [load_spectrum_csv(file_path) for file_path in csv_files]

    result: dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "dry_run": dry_run,
        "csv_files": [str(Path(path)) for path in csv_files],
        "output_path": str(Path(output_path)),
        "written_files": [],
        "spectra": [
            {
                "file_path": item["file_path"],
                "label": item["label"],
                "x_column": item["x_column"],
                "y_column": item["y_column"],
                "row_count": item["row_count"],
            }
            for item in spectra
        ],
    }

    if dry_run:
        result["actions"] = ["load_csv", "plot_linear_and_log"]
        return result

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b", "#e377c2"]

    data_list = []
    for item in spectra:
        data_list.append(
            (
                item["label"],
                pd.Series(item["energy"]),
                pd.Series(item["tally"]),
            )
        )

    for i, (label, x, y) in enumerate(data_list):
        color = colors[i % len(colors)]
        axes[0].plot(x, y, label=label, color=color, lw=1.5, alpha=0.8)
        axes[1].semilogy(x, y, label=label, color=color, lw=1.5, alpha=0.8)

    max_x_valid = []
    for _, x, y in data_list:
        valid_x = x[y > 0]
        if not valid_x.empty:
            max_x_valid.append(valid_x.max())

    plot_max_x = max(max_x_valid) if max_x_valid else 1.6
    max_y = max([y.max() for _, _, y in data_list]) if data_list else 1.0

    for ax in axes:
        ax.set_xlabel("Energy (MeV)", fontsize=12)
        ax.set_ylabel("Tally (Counts/Particle)", fontsize=12)
        ax.legend(loc="upper right")
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.set_xlim(left=0, right=plot_max_x * 1.05)

    axes[0].set_title("Gamma Spectra (Linear Scale)", fontsize=14)
    axes[0].set_ylim(bottom=0, top=max_y * 1.05)
    axes[1].set_title("Gamma Spectra (Log Scale)", fontsize=14)
    axes[1].set_ylim(bottom=max_y * 1e-6, top=max_y * 2.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    result["written_files"] = [str(Path(output_path))]
    return result
