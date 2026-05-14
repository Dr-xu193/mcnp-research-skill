"""MCNP5 compatibility diagnostics / guided repair layer.

Static preflight checks for MCNP5 input decks.  Does NOT simulate or
replace the MCNP5 parser — this is a lightweight hygiene and reference
checker that tells the user *what* is wrong, *where*, and *why* before
MCNP execution.

Target: conservative legacy MCNP5 (e.g. MCNP5_RSICC 1.14).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# version profiles
# ---------------------------------------------------------------------------

MCNP5_CONSERVATIVE = {
    "max_columns": 80,
    "continuation_style": "five_spaces",
    "comment_prefixes": ("c ", "C "),
    "inline_comment": "$",
}
"""Rules for conservative legacy MCNP5 (RSICC 1.14 class)."""

VERSIONS: dict[str, dict[str, Any]] = {
    "mcnp5_rsicc_1_14": MCNP5_CONSERVATIVE,
    "mcnp5_legacy": MCNP5_CONSERVATIVE,
}

# ---------------------------------------------------------------------------
# regex helpers — compiled once
# ---------------------------------------------------------------------------

_CELL_RE = re.compile(r"^(\d+)\s+(\d+)\s+([\d.+\-]+)")
_SURF_RE = re.compile(r"^(\d+)\s+(pz|cz|kz|so|px|py|cx|cy|s|x|y|z|sq|gq|tx|ty|tz|rpp|box|rcc|rec|trc|ell|wed|arb)\b", re.IGNORECASE)
_MATERIAL_RE = re.compile(r"^[mM](\d+)\s+")
_MODE_RE = re.compile(r"^mode\s+", re.IGNORECASE)
_SDEF_RE = re.compile(r"^sdef\s+", re.IGNORECASE)
_NPS_RE = re.compile(r"^nps\s+", re.IGNORECASE)
_F_TALLY_RE = re.compile(r"^[fF](\d+)\s*:\s*([pne/c,]+)\s+", re.IGNORECASE)
_SI_RE = re.compile(r"^[sS][iI](\d+)\s+")
_SP_RE = re.compile(r"^[sS][pP](\d+)\s+")
_TR_CARD_RE = re.compile(r"^[tT][rR](\d+)\s+")
_PRINT_RE = re.compile(r"^print\b", re.IGNORECASE)
_BLANK_RE = re.compile(r"^\s*$")
_COMMENT_C_RE = re.compile(r"^[cC]\s+")
_CONTINUATION_RE = re.compile(r"^ {5,}\S")

# surface ids referenced in cell geometry: digits preceded by non-digit context
_SURF_REF_RE = re.compile(r"(?<![a-zA-Z0-9])(\d+)(?![a-zA-Z0-9])")

# cell ids in cell geometry (for # and explicit refs)
_CELL_REF_RE = re.compile(r"#(\d+)")

# particle mapping
_PARTICLE_MAP: dict[str, set[str]] = {
    "n": {"n", "neutron"},
    "p": {"p", "photon"},
    "e": {"e", "electron"},
}


# ---------------------------------------------------------------------------
# safe punctuation mapping for repair
# ---------------------------------------------------------------------------

_SAFE_PUNCT_MAP: dict[str, str] = {
    "—": "--",   # em dash
    "–": "-",    # en dash
    "→": "->",   # rightwards arrow
    "←": "<-",   # leftwards arrow
    "‘": "'",    # left single quote
    "’": "'",    # right single quote
    "“": '"',    # left double quote
    "”": '"',    # right double quote
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_comment(line: str) -> bool:
    return bool(_COMMENT_C_RE.match(line))


def _is_blank(line: str) -> bool:
    return bool(_BLANK_RE.match(line))


def _is_continuation(line: str) -> bool:
    """A line starting with 5+ spaces and some content is a continuation."""
    return bool(_CONTINUATION_RE.match(line))


def _is_title_line(line: str, idx: int, _lines: list[str]) -> bool:
    """Line 0 that is not a recognised card is the title."""
    return idx == 0 and not any(
        re.match(p, line, re.IGNORECASE)
        for p in (r"^\d+\s+\d+", r"^\d+\s+[a-zA-Z]", r"^mode\s", r"^[mM]\d+\s",
                  r"^sdef\s", r"^[fF]\d+", r"^[eE]\d+", r"^nps\s", r"^print\b")
    )


def _extract_card_ids(lines: list[str]) -> dict[str, set[int]]:
    """Extract surface, cell, material, and tally card ids from deck."""
    surf_ids: set[int] = set()
    cell_ids: set[int] = set()
    mat_ids: set[int] = set()
    tr_ids: set[int] = set()
    si_ids: set[int] = set()
    sp_ids: set[int] = set()
    f_tallies: dict[int, str] = {}  # id → raw card
    mode_particles: list[str] = []
    sdef_params: str = ""

    for line in lines:
        stripped = line.strip()
        if _is_comment(line) or _is_blank(line) or _is_continuation(line):
            continue

        # surface card: number followed by type keyword
        sm = _SURF_RE.match(stripped)
        if sm:
            surf_ids.add(int(sm.group(1)))
            continue

        # cell card: number followed by material
        cm = _CELL_RE.match(stripped)
        if cm:
            cell_ids.add(int(cm.group(1)))
            continue

        # material card
        mm = _MATERIAL_RE.match(stripped)
        if mm:
            mat_ids.add(int(mm.group(1)))
            continue

        # mode card
        if _MODE_RE.match(stripped):
            parts = stripped.lower().replace("mode", "").split()
            mode_particles = [p.strip() for p in parts]
            continue

        # tr card
        tm = _TR_CARD_RE.match(stripped)
        if tm:
            tr_ids.add(int(tm.group(1)))
            continue

        # SI card
        sim = _SI_RE.match(stripped)
        if sim:
            si_ids.add(int(sim.group(1)))
            continue

        # SP card
        spm = _SP_RE.match(stripped)
        if spm:
            sp_ids.add(int(spm.group(1)))
            continue

        # F tally
        fm = _F_TALLY_RE.match(stripped)
        if fm:
            f_tallies[int(fm.group(1))] = stripped
            continue

        # SDEF — capture full line for later par= check
        if _SDEF_RE.match(stripped):
            sdef_params = stripped.lower()
            continue

    return {
        "surfaces": surf_ids,
        "cells": cell_ids,
        "materials": mat_ids,
        "tr": tr_ids,
        "si": si_ids,
        "sp": sp_ids,
        "f_tallies": f_tallies,
        "mode_particles": mode_particles,
        "sdef_params": sdef_params,
    }


def _extract_cell_surface_refs(cell_line: str) -> set[int]:
    """Find surface ids referenced in a cell card geometry expression."""
    ids: set[int] = set()
    stripped = cell_line.strip()

    # Parse: cell_id material [density] geom [keyword modifiers...]
    # Material 0 = void, no density follows
    parts = stripped.split()
    if len(parts) < 3:
        return ids
    try:
        mat_id = int(parts[1])
    except ValueError:
        return ids
    # geometry starts at index 2 (void) or 3 (material with density)
    geom_start = 2 if mat_id == 0 else 3
    if geom_start >= len(parts):
        return ids

    # Collect geometry parts up to the first keyword modifier
    geom_tokens: list[str] = []
    for tok in parts[geom_start:]:
        lower = tok.lower()
        if any(
            lower.startswith(kw)
            for kw in ("imp:", "vol=", "trcl=", "tmp=", "u=", "fill=")
        ):
            break
        geom_tokens.append(tok)

    rest = " ".join(geom_tokens)
    for m in _SURF_REF_RE.finditer(rest):
        ids.add(int(m.group(1)))
    for m in _CELL_REF_RE.finditer(rest):
        ids.add(int(m.group(1)))
    return ids


def _build_issue(
    code: str,
    severity: str,
    line: int,
    mcnp_version: str,
    observed: str,
    expected: str,
    auto_fixable: bool,
    suggested_fix: str,
    user_explanation: str,
    topics: list[str],
    instruction_zh: str,
    column: int | None = None,
    column_range: tuple[int, int] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "line": line,
        "column": column,
        "column_range": list(column_range) if column_range else None,
        "message": f"{code}: {observed}",
        "mcnp_version": mcnp_version,
        "observed": observed,
        "expected": expected,
        "auto_fixable": auto_fixable,
        "suggested_fix": suggested_fix,
        "user_explanation": user_explanation,
        "ai_guidance": {
            "mcnp_version_assumed": mcnp_version,
            "topics_to_review": topics,
            "instruction": instruction_zh,
        },
    }


def _severity_order(severity: str) -> int:
    return {"blocking": 0, "error": 1, "warning": 2}.get(severity, 3)


# ===================================================================
# diagnose_deck
# ===================================================================

def diagnose_deck(
    text: str,
    *,
    mcnp_version: str = "mcnp5_rsicc_1_14",
) -> dict[str, Any]:
    """Run all MCNP5 compatibility diagnostics on *text*.

    Returns a structured result with ``issues`` list, ``summary``, and
    ``ok`` flag.  ``ok`` is ``False`` when any blocking issue exists.
    """
    rules = VERSIONS.get(mcnp_version, MCNP5_CONSERVATIVE)
    max_cols: int = rules["max_columns"]
    issues: list[dict[str, Any]] = []

    lines = text.splitlines()
    # Preserve trailing newline status for each line
    line_ends = []
    raw_lines = text.split("\n")
    for rl in raw_lines:
        line_ends.append("\n")

    # ---- 1. line length ----
    for i, line in enumerate(lines):
        length = len(line.rstrip("\n"))
        if length > max_cols:
            issues.append(_build_issue(
                code="LINE_TOO_LONG",
                severity="error",
                line=i + 1,
                mcnp_version=mcnp_version,
                observed=f"line {i+1} has {length} columns",
                expected=f"≤ {max_cols} columns",
                auto_fixable=_is_safe_to_continue(line),
                suggested_fix="使用 MCNP5 continuation（下一行以 5 个空格起头）拆分长行"
                if _is_safe_to_continue(line)
                else "手工拆行或检查 MCNP5 输入格式",
                user_explanation=f"第 {i+1} 行 {length} 列超过 MCNP5 的 {max_cols} 列限制。",
                topics=["MCNP5 input card 80 columns", "MCNP5 continuation line"],
                instruction_zh="查阅 MCNP5 输入手册的 continuation 规则后，在合法位置拆行。",
                column=length,
            ))

    # ---- 2. tabs ----
    for i, line in enumerate(lines):
        tab_cols = [j for j, ch in enumerate(line) if ch == "\t"]
        if tab_cols:
            issues.append(_build_issue(
                code="TAB_CHARACTER",
                severity="error",
                line=i + 1,
                mcnp_version=mcnp_version,
                observed=f"line {i+1} contains {len(tab_cols)} tab character(s)",
                expected="spaces only",
                auto_fixable=True,
                suggested_fix="将 tab 替换为空格",
                user_explanation=f"第 {i+1} 行包含 tab 字符。MCNP5 不允许 tab。",
                topics=["MCNP5 input format", "MCNP5 card columns"],
                instruction_zh="用空格替换 tab，保持 card 对齐。",
                column=tab_cols[0] + 1 if tab_cols else None,
                column_range=(tab_cols[0] + 1, tab_cols[-1] + 2) if tab_cols else None,
            ))

    # ---- 3. card start column ----
    _CARD_KEYWORDS_RE = re.compile(
        r"^(mode|sdef|nps|print|tr|si|sp|f\d+|e\d+|m\d+|ft\d+|fc\d+|fm\d+|fq\d+|fu\d+|fs\d+|fw\d+)",
        re.IGNORECASE,
    )
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or _is_comment(line) or _is_blank(line):
            continue
        if _is_title_line(line, i, lines):
            continue
        # If it starts with 5+ spaces but looks like a primary card keyword,
        # this is a misplaced card, not a valid continuation
        lead = len(line) - len(line.lstrip(" "))
        is_cont = _is_continuation(line)
        if is_cont and _CARD_KEYWORDS_RE.match(stripped):
            # Restore: force detection as a misplaced card
            is_cont = False
        if is_cont:
            continue
        if lead > 5:
            # Only flag if it looks like a card (not a long comment or $ comment)
            if not line.lstrip().startswith(("$",)):
                issues.append(_build_issue(
                    code="CARD_START_COLUMN",
                    severity="warning",
                    line=i + 1,
                    mcnp_version=mcnp_version,
                    observed=f"line {i+1} card starts at column {lead + 1}",
                    expected="card name/number within first 5 columns",
                    auto_fixable=False,
                    suggested_fix="将 card 标识符移到第 1-5 列",
                    user_explanation=f"第 {i+1} 行的 card 从第 {lead + 1} 列开始，MCNP5 要求 card 名称在前 5 列内。",
                    topics=["MCNP5 input card columns", "MCNP5 card name placement"],
                    instruction_zh="检查该行是否为有意缩进的数据卡。若是，移到前 5 列。",
                    column=lead + 1,
                ))

    # ---- 4. continuation validity ----
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_continuation(line) and stripped:
            # continuation that looks like a comment
            if _is_comment(stripped) or stripped.startswith("$"):
                issues.append(_build_issue(
                    code="INVALID_CONTINUATION",
                    severity="error",
                    line=i + 1,
                    mcnp_version=mcnp_version,
                    observed=f"line {i+1} starts with 5+ spaces but appears to be a comment",
                    expected="continuation lines must carry card content, not comments",
                    auto_fixable=False,
                    suggested_fix="将注释移到独立 comment card（c ...）",
                    user_explanation=f"第 {i+1} 行看起来像 continuation 但内容是注释。",
                    topics=["MCNP5 continuation line", "MCNP5 comment card"],
                    instruction_zh="确认该行意图：若是注释，改为 'c ...' 格式。",
                ))

    # ---- 5. non-ASCII characters ----
    _NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")
    has_chinese_anywhere = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        is_comm = _is_comment(line)
        is_title = _is_title_line(line, i, lines)
        has_cjk = bool(re.search(r"[一-鿿㐀-䶿豈-﫿]", line))
        if has_cjk:
            has_chinese_anywhere = True

        has_non_ascii = bool(_NON_ASCII_RE.search(line))

        # 5a. non-ASCII in title card
        if is_title and has_non_ascii:
            issues.append(_build_issue(
                code="NON_ASCII_TITLE_CARD",
                severity="error",
                line=i + 1,
                mcnp_version=mcnp_version,
                observed=f"title line {i+1} contains non-ASCII characters",
                expected="title card should be ASCII-only for legacy MCNP5 compatibility",
                auto_fixable=True,
                suggested_fix="将 Unicode 标点替换为 ASCII 等价形式（— → --, → → ->，等）",
                user_explanation=f"第 {i+1} 行 title 包含非 ASCII 字符。老版本 MCNP5 可能将 title 行编码风险导致读取错误。",
                topics=["MCNP5 title card", "MCNP5 input encoding"],
                instruction_zh="将 title 中的非 ASCII 标点替换为 ASCII 等价物（— → --, → → ->）。",
            ))
            continue  # handled as title

        # 5b. non-ASCII in data/cell/surface cards
        if has_non_ascii and not is_comm and not is_title:
            # Check if non-ASCII is only in $ inline comment portion
            dollar_pos = line.find("$")
            if dollar_pos >= 0:
                before_dollar = line[:dollar_pos]
                after_dollar = line[dollar_pos:]
                if not _NON_ASCII_RE.search(before_dollar):
                    # Non-ASCII only in inline comment — still warn for data cards
                    issues.append(_build_issue(
                        code="NON_ASCII_DATA_CARD",
                        severity="warning",
                        line=i + 1,
                        mcnp_version=mcnp_version,
                        observed=f"data card line {i+1} has non-ASCII in $ inline comment",
                        expected="$ inline comments should use ASCII for legacy MCNP5",
                        auto_fixable=True,
                        suggested_fix="将 $ 注释中的 Unicode 标点替换为 ASCII 等价形式",
                        user_explanation=f"第 {i+1} 行 data card 的 $ 注释中包含非 ASCII 字符。低版本 MCNP5 可能无法正确处理。",
                        topics=["MCNP5 comment card", "MCNP5 input encoding"],
                        instruction_zh="将 $ 注释中的 Unicode 替换为 ASCII。",
                    ))
                    continue
            # Non-ASCII in actual card content
            issues.append(_build_issue(
                code="NON_ASCII_DATA_CARD",
                severity="error",
                line=i + 1,
                mcnp_version=mcnp_version,
                observed=f"data card line {i+1} contains non-ASCII characters in card content",
                expected="cell/surface/data cards must be ASCII-only",
                auto_fixable=False,
                suggested_fix="手工检查并替换该行中的非 ASCII 字符",
                user_explanation=f"第 {i+1} 行 data card 内容中包含非 ASCII 字符。MCNP5 无法解析此数据。",
                topics=["MCNP5 input format", "MCNP5 input encoding"],
                instruction_zh="检查该行的非 ASCII 字符来源。不要改动物理值。",
            ))

        # 5c. Chinese characters anywhere → encoding risk warning
        if has_cjk and (is_comm or is_title):
            # Already handled; risk is tagged below
            pass

    if has_chinese_anywhere:
        issues.append(_build_issue(
            code="CHINESE_COMMENT_ENCODING_RISK",
            severity="warning",
            line=0,
            mcnp_version=mcnp_version,
            observed="deck contains Chinese characters",
            expected="ensure encoding compatible with MCNP5 (ASCII/Latin-1 preferred)",
            auto_fixable=False,
            suggested_fix="确认运行环境的 MCNP5 是否支持 UTF-8 编码的 comment 行",
            user_explanation="此 deck 包含中文注释。老版本 MCNP5 可能要求 ASCII 编码。",
            topics=["MCNP5 input encoding", "MCNP5 comment card"],
            instruction_zh="如果 MCNP5 报错读取失败，将文件转为纯 ASCII 或 Latin-1 编码。",
        ))

    # ---- 6. block structure ----
    # Expected: title → cells → blank → surfaces → blank → data
    _check_block_structure(lines, issues, mcnp_version)

    # ---- 7. reference checks ----
    ids = _extract_card_ids(lines)
    _check_references(lines, ids, issues, mcnp_version)

    # ---- 8. MODE / tally / source consistency ----
    _check_mode_consistency(ids, issues, mcnp_version)

    # ---- sort and summarise ----
    issues.sort(key=lambda x: (x["line"], _severity_order(x["severity"])))
    summary = {
        "total": len(issues),
        "blocking": sum(1 for i in issues if i["severity"] == "blocking"),
        "errors": sum(1 for i in issues if i["severity"] == "error"),
        "warnings": sum(1 for i in issues if i["severity"] == "warning"),
        "fixable": sum(1 for i in issues if i["auto_fixable"]),
    }

    return {
        "ok": summary["blocking"] == 0,
        "mcnp_version": mcnp_version,
        "issues": issues,
        "summary": summary,
    }


# ===================================================================
# internal check helpers
# ===================================================================

def _is_safe_to_continue(line: str) -> bool:
    """Heuristic: can this line be safely continued with 5-space continuation?

    Cell/surface definitions are NOT safely continuable because boolean
    expressions (#, :) are position-sensitive.  Data cards (materials,
    SDEF, SI, SP, etc.) ARE safe.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Cell cards: start with digit, then material
    if _CELL_RE.match(stripped):
        return False  # cell geometry is complex
    if _SURF_RE.match(stripped):
        return False  # surface definition is simple, but continuation is unusual
    # Data cards are generally safe
    return True


def _find_section_break(lines: list[str], start: int) -> int | None:
    """Find the next blank-line-delimited section boundary after *start*."""
    for i in range(start, len(lines)):
        if _is_blank(lines[i]):
            return i
    return None


def _check_block_structure(
    lines: list[str], issues: list[dict], mcnp_version: str
) -> None:
    """Check for proper MCNP deck block structure."""
    # Find sections
    title_end = 1  # line 0 is title, skip it
    cell_start = title_end
    cell_end: int | None = None
    surf_start: int | None = None
    surf_end: int | None = None
    data_start: int | None = None

    # Scan for first blank line → cell/surface boundary
    for i in range(1, len(lines)):
        if _is_blank(lines[i]) and cell_end is None:
            cell_end = i
            surf_start = i + 1
            continue
        if _is_blank(lines[i]) and cell_end is not None and surf_end is None:
            surf_end = i
            data_start = i + 1
            break

    # If we couldn't find clear section boundaries with blank lines
    if cell_end is None:
        issues.append(_build_issue(
            code="MISSING_BLOCK_DELIMITER",
            severity="warning",
            line=0,
            mcnp_version=mcnp_version,
            observed="cannot locate blank-line delimiter between cell cards and surface cards",
            expected="cell cards → blank line → surface cards → blank line → data cards",
            auto_fixable=False,
            suggested_fix="在 cell cards 和 surface cards 之间插入一个空行",
            user_explanation="MCNP5 deck 通常以空行分隔 cell / surface / data 三个区块。找不到清晰分隔可能导致解析错误。",
            topics=["MCNP5 deck structure", "MCNP5 input blocks"],
            instruction_zh="检查 deck 的结构：title → cells → 空行 → surfaces → 空行 → data。",
        ))


def _check_references(
    lines: list[str], ids: dict, issues: list[dict], mcnp_version: str
) -> None:
    """Check basic cell/surface/material/tally references."""
    cells = ids["cells"]
    surfaces = ids["surfaces"]
    materials = ids["materials"]
    f_tallies: dict[int, str] = ids["f_tallies"]

    # F8 tally cell references
    for fid, raw in f_tallies.items():
        # Parse cell references: after the particle list, before next keyword
        # f8:p,e 104  or f8:p 101 102 103
        parts = raw.split()
        # parts[0] = f8:p,e or similar
        tally_cells = []
        for p in parts[1:]:
            # Skip if it looks like a modifier
            if p.lower() in ("t", "f", "d", "u", "s", "c", "e"):
                continue
            # Skip T modifier like "104t"
            m = re.match(r"^(\d+)", p)
            if m:
                tally_cells.append(int(m.group(1)))
        for tc in tally_cells:
            if tc not in cells:
                issues.append(_build_issue(
                    code="UNKNOWN_TALLY_CELL_REFERENCE",
                    severity="blocking",
                    line=0,  # will be set by caller if line info available
                    mcnp_version=mcnp_version,
                    observed=f"F{fid} tally references cell {tc} which does not exist",
                    expected=f"cell {tc} to be defined in cell cards section",
                    auto_fixable=False,
                    suggested_fix=f"确认 cell {tc} 是否存在；如果不存在，修改 F{fid} 引用",
                    user_explanation=f"F{fid} tally 引用了不存在的 cell {tc}。MCNP5 会报 fatal error。",
                    topics=["MCNP5 F tally", "MCNP5 cell cards"],
                    instruction_zh="检查 cell cards 区块，确认是否存在 cell {tc}。如果不确定，查阅原始 deck 或 MCNP 手册。",
                ))

    # cell → surface references
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not _CELL_RE.match(stripped):
            continue
        refs = _extract_cell_surface_refs(stripped)
        for ref in refs:
            # Skip material-like numbers (density, etc.)
            if ref in cells or ref in materials:
                continue
            if ref not in surfaces:
                issues.append(_build_issue(
                    code="UNKNOWN_SURFACE_REFERENCE",
                    severity="blocking",
                    line=i + 1,
                    mcnp_version=mcnp_version,
                    observed=f"cell card references surface {ref} which is not defined",
                    expected=f"surface {ref} to be defined in surface cards section",
                    auto_fixable=False,
                    suggested_fix=f"确认 surface {ref} 是否已在 surface cards 区块定义",
                    user_explanation=f"第 {i+1} 行 cell 引用了不存在的 surface {ref}。MCNP5 会报 fatal error。",
                    topics=["MCNP5 surface cards", "MCNP5 cell geometry"],
                    instruction_zh="检查 surface cards 区块是否存在 surface {ref}。如果不确定，查阅原始 geometry 定义。",
                ))

    # cell → material references
    for i, line in enumerate(lines):
        stripped = line.strip()
        cm = _CELL_RE.match(stripped)
        if not cm:
            continue
        mat_id = int(cm.group(2))
        if mat_id == 0:
            continue  # void
        if mat_id not in materials:
            issues.append(_build_issue(
                code="UNKNOWN_MATERIAL_REFERENCE",
                severity="blocking",
                line=i + 1,
                mcnp_version=mcnp_version,
                observed=f"cell uses material {mat_id} which is not defined",
                expected=f"material m{mat_id} to be in data cards section",
                auto_fixable=False,
                suggested_fix=f"定义 m{mat_id} material card 或修正 cell 的 material id",
                user_explanation=f"第 {i+1} 行 cell 使用了未定义的 material {mat_id}。",
                topics=["MCNP5 material cards", "MCNP5 cell cards"],
                instruction_zh="检查 data cards 区块，确认 m{mat_id} 是否存在。",
            ))


def _check_mode_consistency(
    ids: dict, issues: list[dict], mcnp_version: str
) -> None:
    """Check MODE vs tally/source particle consistency."""
    mode = set(ids["mode_particles"])
    f_tallies: dict[int, str] = ids["f_tallies"]
    sdef = ids["sdef_params"]

    if not mode:
        return  # no MODE card — let MCNP handle defaults

    # MODE vs F tally particles
    for fid, raw in f_tallies.items():
        # Parse particle list: f8:p,e → ["p", "e"]
        parts = raw.split()
        if len(parts) < 1:
            continue
        particle_part = parts[0].split(":", 1)[-1] if ":" in parts[0] else ""
        if not particle_part:
            continue
        tally_particles = set(particle_part.lower().replace(" ", "").split(","))
        for tp in tally_particles:
            if tp not in mode and tp in _PARTICLE_MAP:
                # map to canonical mode names
                mode_names = _PARTICLE_MAP.get(tp, set())
                if not mode_names & mode:
                    issues.append(_build_issue(
                        code="MODE_TALLY_MISMATCH",
                        severity="warning",
                        line=0,
                        mcnp_version=mcnp_version,
                        observed=f"F{fid} uses particle '{tp}' but MODE={list(mode)} does not include it",
                        expected=f"MODE to include '{tp}' for F{fid} tally",
                        auto_fixable=False,
                        suggested_fix="如果确实需要该 tally，添加对应粒子到 MODE card",
                        user_explanation=f"F{fid} tally 请求粒子 '{tp}' 但 MODE 中未包含。MCNP5 可能忽略此 tally 或报错。",
                        topics=["MCNP5 MODE card", "MCNP5 F tally"],
                        instruction_zh="确认物理模型是否需要该粒子。若需要，修改 MODE card 包含对应粒子。",
                    ))

    # MODE vs SDEF par
    if sdef:
        pm = re.search(r"par=(\d+)", sdef)
        if pm:
            par = int(pm.group(1))
            # par=1 n, par=2 p, par=3 e
            par_to_mode = {1: "n", 2: "p", 3: "e"}
            expected_mode = par_to_mode.get(par)
            if expected_mode and expected_mode not in mode:
                issues.append(_build_issue(
                    code="MODE_SOURCE_MISMATCH",
                    severity="warning",
                    line=0,
                    mcnp_version=mcnp_version,
                    observed=f"SDEF par={par} ({expected_mode}) but MODE={list(mode)}",
                    expected=f"MODE to include '{expected_mode}' for source particle",
                    auto_fixable=False,
                    suggested_fix=f"添加 '{expected_mode}' 到 MODE card",
                    user_explanation=f"SDEF 发射粒子类型 par={par}，但 MODE 中未包含对应粒子。",
                    topics=["MCNP5 MODE card", "MCNP5 SDEF source"],
                    instruction_zh="确认源粒子类型。若 SDEF 正确，修改 MODE card 包含对应粒子。",
                ))


# ===================================================================
# repair_deck
# ===================================================================

def repair_deck(
    text: str,
    *,
    mcnp_version: str = "mcnp5_rsicc_1_14",
) -> dict[str, Any]:
    """Apply safe automatic fixes to *text*.

    Only fixes format issues: tabs→spaces, safe line-too-long→continuation,
    naked non-ASCII lines→comment cards.  Does NOT modify geometry, physics,
    tally definitions, or material compositions.

    Returns repaired text, change_log, and before/after diagnostics.
    """
    rules = VERSIONS.get(mcnp_version, MCNP5_CONSERVATIVE)
    max_cols: int = rules["max_columns"]
    change_log: list[dict[str, Any]] = []

    diag_before = diagnose_deck(text, mcnp_version=mcnp_version)

    lines = text.split("\n")
    new_lines: list[str] = []
    line_number = 0

    i = 0
    while i < len(lines):
        line_number += 1
        line = lines[i]

        # --- fix: tabs → spaces ----
        if "\t" in line:
            before = line
            # Replace tabs with spaces, try to preserve alignment (4-space tab stops)
            new_line = ""
            col = 0
            for ch in line:
                if ch == "\t":
                    spaces = 4 - (col % 4)
                    new_line += " " * spaces
                    col += spaces
                else:
                    new_line += ch
                    col += 1
            line = new_line
            change_log.append({
                "line": line_number, "code": "TAB_CHARACTER",
                "before": before.rstrip("\n"), "after": line.rstrip("\n"),
                "reason": "tab(s) replaced with spaces",
            })

        # --- fix: line too long (safe continuation) ----
        if len(line.rstrip("\n")) > max_cols and _is_safe_to_continue(line):
            before = line.rstrip("\n")
            # Split at last space before column limit
            limit = max_cols
            if len(line) > limit:
                split_at = line.rfind(" ", 0, limit)
                if split_at < limit // 2:  # No good split point
                    split_at = limit
                part1 = line[:split_at].rstrip()
                part2 = line[split_at:].lstrip()
                # Continuation: next line starts with 5 spaces
                line = part1
                continuation = "     " + part2
                new_lines.append(line)
                change_log.append({
                    "line": line_number, "code": "LINE_TOO_LONG",
                    "before": before, "after": f"{part1}\\n{continuation}",
                    "reason": f"line {line_number} exceeded {max_cols} columns, split with continuation",
                })
                # Insert continuation after this line
                line_number += 1
                # Check if continuation itself needs splitting
                if len(continuation) > max_cols:
                    # Recursive split would be needed, just flag
                    new_lines.append(continuation)
                else:
                    new_lines.append(continuation)
                i += 1
                continue

        # --- fix: non-ASCII punctuation in title / comments ----
        _NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")
        if _NON_ASCII_RE.search(line):
            stripped = line.strip()
            is_title = line_number == 1  # first line is always title
            is_comm = _is_comment(line)
            dollar_pos = line.find("$")

            # Safe zones for punctuation replacement: title, c-comments, $ inline comments
            safe_zone = is_title or is_comm or (dollar_pos >= 0 and not _CELL_RE.match(stripped) and not _SURF_RE.match(stripped))

            if safe_zone:
                before = line.rstrip("\n")
                new_line = line
                for uni_ch, ascii_ch in _SAFE_PUNCT_MAP.items():
                    if uni_ch in new_line:
                        new_line = new_line.replace(uni_ch, ascii_ch)
                if new_line != line:
                    line = new_line
                    change_log.append({
                        "line": line_number, "code": "NON_ASCII_TITLE_CARD" if is_title else "NON_ASCII_DATA_CARD",
                        "before": before.rstrip("\n"), "after": line.rstrip("\n"),
                        "reason": "non-ASCII punctuation replaced with ASCII equivalent",
                    })

        # --- fix: bare Chinese / non-ASCII data line → comment ----
        has_cjk = bool(re.search(r"[一-鿿㐀-䶿豈-﫿]", line))
        if has_cjk:
            stripped = line.strip()
            if stripped and not _is_comment(line) and not _is_blank(line):
                if _CELL_RE.match(stripped) or _SURF_RE.match(stripped) or _MATERIAL_RE.match(stripped):
                    pass  # Has CJK in a card — don't touch
                elif not _is_title_line(line, i, lines):
                    before = line.rstrip("\n")
                    line = "c " + stripped if not stripped.startswith(("c ", "C ")) else line
                    if before != line.rstrip("\n"):
                        change_log.append({
                            "line": line_number, "code": "NON_ASCII_DATA_CARD",
                            "before": before, "after": line.rstrip("\n"),
                            "reason": "bare non-ASCII line converted to c comment card",
                        })

        new_lines.append(line)
        i += 1

    repaired_text = "\n".join(new_lines)

    # Handle missing trailing newline
    if text and not text.endswith("\n"):
        repaired_text = "\n".join(new_lines)

    diag_after = diagnose_deck(repaired_text, mcnp_version=mcnp_version)

    unfixable = [i for i in diag_after["issues"] if not i["auto_fixable"] and i["severity"] in ("error", "blocking")]

    return {
        "ok": True,
        "mcnp_version": mcnp_version,
        "repaired": len(change_log) > 0,
        "text": repaired_text,
        "change_log": change_log,
        "change_count": len(change_log),
        "diagnostics_before": diag_before,
        "diagnostics_after": diag_after,
        "unfixable_issues": unfixable,
    }


# ===================================================================
# file-level convenience
# ===================================================================

def diagnose_deck_file(
    input_path: str | Path,
    *,
    mcnp_version: str = "mcnp5_rsicc_1_14",
) -> dict[str, Any]:
    """Read *input_path* and run :func:`diagnose_deck`."""
    path = Path(input_path)
    if not path.is_file():
        return {
            "ok": False,
            "errors": [{"code": "INPUT_FILE_NOT_FOUND", "message": str(path)}],
            "mcnp_version": mcnp_version,
            "issues": [],
            "summary": {"total": 0, "blocking": 0, "errors": 0, "warnings": 0, "fixable": 0},
        }
    text = path.read_text(encoding="utf-8")
    return diagnose_deck(text, mcnp_version=mcnp_version)


def repair_deck_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    mcnp_version: str = "mcnp5_rsicc_1_14",
) -> dict[str, Any]:
    """Read, repair, and write a deck file."""
    in_path = Path(input_path)
    out_path = Path(output_path)
    if not in_path.is_file():
        return {
            "ok": False,
            "errors": [{"code": "INPUT_FILE_NOT_FOUND", "message": str(in_path)}],
            "repaired": False,
            "change_log": [],
            "change_count": 0,
        }
    text = in_path.read_text(encoding="utf-8")
    result = repair_deck(text, mcnp_version=mcnp_version)
    if result["repaired"]:
        out_path.write_text(result["text"], encoding="utf-8")
    else:
        # Copy unchanged
        out_path.write_text(text, encoding="utf-8")
    result["input_path"] = str(in_path)
    result["output_path"] = str(out_path)
    return result
