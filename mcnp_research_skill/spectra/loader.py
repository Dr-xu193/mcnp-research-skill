"""CSV spectrum loading utilities migrated from the legacy SpectraEngine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd


def load_spectrum_csv(file_path: str) -> dict[str, Any]:
    """Load a spectrum CSV and identify energy/count columns.

    The column-selection behavior intentionally mirrors
    ``legacy.auto.SpectraEngine.load_data``:

    - first column containing ``energy`` or ``mev`` is used as x data
    - first column containing ``tally`` or ``count`` is used as y data
    - if either column is not found, the first or second CSV column is used
    - label comes from the filename stem, truncated through the first ``cm``
    """
    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()

        if len(df.columns) < 2:
            raise ValueError("CSV must contain at least two columns")

        x_cols = [c for c in df.columns if "energy" in c.lower() or "mev" in c.lower()]
        y_cols = [c for c in df.columns if "tally" in c.lower() or "count" in c.lower()]

        x_column = x_cols[0] if x_cols else df.columns[0]
        y_column = y_cols[0] if y_cols else df.columns[1]
        x_data = df[x_column]
        y_data = df[y_column]

        label = os.path.splitext(os.path.basename(file_path))[0]
        cm_idx = label.lower().find("cm")
        if cm_idx != -1:
            label = label[: cm_idx + 2]

        return {
            "ok": True,
            "file_path": str(Path(file_path)),
            "label": label,
            "x_column": str(x_column),
            "y_column": str(y_column),
            "energy": x_data.tolist(),
            "tally": y_data.tolist(),
            "row_count": int(len(df)),
        }
    except Exception as exc:
        raise ValueError(f"文件读取失败: {exc}") from exc
