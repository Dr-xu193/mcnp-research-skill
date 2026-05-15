"""MCNP5 front-of-output failure analyzer.

Parses the first N lines of MCNP output (default 300) to identify
fatal errors, warnings, and common failure patterns.  Combines findings
with workflow context (model, source strategy, tally, postprocess) to
produce actionable Chinese-language diagnostics.

Does NOT parse the full output file.  Does NOT simulate or replace the
MCNP5 parser.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# pattern database — (code, category, priority, regex)
# priority: higher = checked first, 1=fatal 2=error 3=warning 4=info
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, str, int, str]] = [
    # --- fatal / termination ---
    ("MCNP_FATAL_ERROR", "fatal", 1, r"fatal\s*error"),
    ("MCNP_BAD_TROUBLE", "fatal", 1, r"bad\s+trouble"),
    ("MCNP_TERMINATED", "fatal", 1, r"(?:run|execution)\s+terminated"),
    # --- input format ---
    ("MCNP_LINE_TOO_LONG", "input_format", 2, r"line\s+too\s+long|too\s+many\s+characters"),
    ("MCNP_ILLEGAL_CHARACTER", "input_format", 2, r"illegal\s+character"),
    ("MCNP_BAD_CONTINUATION", "input_format", 2, r"bad\s+continuation|continuation"),
    ("MCNP_CARD_FORMAT_ERROR", "input_format", 2, r"card\s+format|input\s+card\s+error"),
    ("MCNP_INPUT_READ_FAILED", "input_format", 2, r"cannot\s+read|bad\s+input|unexpected\s+end"),
    # --- cell / surface / geometry ---
    ("MCNP_UNKNOWN_SURFACE", "geometry", 2, r"undefined\s+surface|surface\s+not\s+found"),
    ("MCNP_UNKNOWN_CELL", "geometry", 2, r"cell\s+not\s+found|bad\s+cell|undefined\s+cell"),
    ("MCNP_GEOMETRY_ERROR", "geometry", 2, r"geometry\s+error|overlap"),
    ("MCNP_LOST_PARTICLE", "geometry", 3, r"lost\s+particle|particle\s+lost"),
    # --- material / xsdir ---
    ("MCNP_UNKNOWN_MATERIAL", "material", 2, r"bad\s+material|missing\s+material"),
    ("MCNP_ZAID_ERROR", "material", 2, r"zaid"),
    ("MCNP_XS_LIBRARY_NOT_FOUND", "material", 2, r"xsdir|library\s+not\s+found|cross[\s-]section"),
    # --- tally ---
    ("MCNP_TALLY_ERROR", "tally", 2, r"bad\s+tally|tally\s+error"),
    ("MCNP_TALLY_REFERENCE_ERROR", "tally", 2, r"tally\s+cell|tally\s+surface"),
    # --- source ---
    ("MCNP_SOURCE_ERROR", "source", 2, r"bad\s+source|source\s+error"),
    ("MCNP_SDEF_ERROR", "source", 2, r"sdef"),
    ("MCNP_SOURCE_DISTRIBUTION_ERROR", "source", 2, r"source\s+distribution"),
    ("MCNP_TRANSFORM_ERROR", "source", 2, r"transform"),
    # --- mode / particle ---
    ("MCNP_MODE_PARTICLE_MISMATCH", "mode", 2, r"not\s+in\s+mode|tally\s+particle|source\s+particle"),
    # --- version info ---
    ("MCNP_VERSION_DETECTED", "info", 4, r"Thread\s+Name\s+&\s+Version\s*=\s*(.+)"),
    ("MCNP_RUN_COMPLETED", "info", 4, r"normal\s+termination|run\s+completed|mcnp\s+completed"),
    # --- warning ---
    ("MCNP_WARNING", "warning", 3, r"\bwarning\b"),
    ("MCNP_ERROR", "error", 2, r"\berror\b"),
]


def _analyze_front_matter(text: str, front_lines: int) -> dict[str, Any]:
    """Scan the first *front_lines* of *text* for MCNP patterns."""
    lines = text.splitlines()
    total = len(lines)
    to_scan = lines[:front_lines]
    findings: list[dict] = []
    version_info: str | None = None

    for lineno, line in enumerate(to_scan, 1):
        for code, category, priority, pattern in _PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                if code == "MCNP_VERSION_DETECTED":
                    version_info = m.group(1).strip()
                    continue
                findings.append({
                    "code": code,
                    "category": category,
                    "priority": priority,
                    "line": lineno,
                    "evidence": line.strip()[:200],
                    "match": m.group(0),
                })

    # Deduplicate by code (keep first occurrence)
    seen: set[str] = set()
    unique: list[dict] = []
    for f in findings:
        if f["code"] not in seen:
            seen.add(f["code"])
            unique.append(f)
    unique.sort(key=lambda x: x["priority"])

    return {
        "total_lines": total,
        "front_lines_analyzed": min(front_lines, total),
        "findings": unique,
        "mcnp_version_detected": version_info,
    }


def analyze_mcnp_failure(
    output_text: str | None = None,
    stdout_text: str | None = None,
    stderr_text: str | None = None,
    returncode: int | None = None,
    context: dict[str, Any] | None = None,
    mcnp_version: str = "mcnp5_rsicc_1_14",
    front_lines: int = 300,
    tail_lines: int = 120,
) -> dict[str, Any]:
    """Analyze MCNP output/stderr/stdout for failure diagnosis.

    By default scans the first *front_lines* of *output_text*.
    Falls back to stderr/stdout/tail if front matter is clean but
    the process exited non-zero.
    """
    result: dict[str, Any] = {
        "ok": True,
        "mcnp_version_assumed": mcnp_version,
        "front_lines_analyzed": 0,
        "total_output_lines": 0,
        "fallback_used": False,
        "findings": [],
        "context": context or {},
        "suggestions": [],
        "status": "unknown",
    }

    front = None
    if output_text:
        front = _analyze_front_matter(output_text, front_lines)
        result["total_output_lines"] = front["total_lines"]
        result["front_lines_analyzed"] = front["front_lines_analyzed"]
        result["findings"] = front["findings"]
        if front["mcnp_version_detected"]:
            result["mcnp_version_detected"] = front["mcnp_version_detected"]

    # Determine status
    has_fatal = any(f["priority"] <= 1 for f in result["findings"])
    has_error = any(f["priority"] <= 2 for f in result["findings"])
    has_warning = any(f["priority"] <= 3 for f in result["findings"])
    completed = any(f["code"] == "MCNP_RUN_COMPLETED" for f in result["findings"])

    if has_fatal or (returncode is not None and returncode != 0):
        result["status"] = "failed"
    elif has_error:
        result["status"] = "error"
    elif has_warning:
        result["status"] = "warning"
    elif completed:
        result["status"] = "completed"
    else:
        result["status"] = "unknown"

    # Fallback: no findings in front matter but non-zero returncode
    if not result["findings"] and returncode is not None and returncode != 0:
        result["fallback_used"] = True
        # Check stderr
        if stderr_text:
            stderr_issues = _scan_for_runtime_issues(stderr_text)
            result["findings"].extend(stderr_issues)
        # Check stdout
        if stdout_text and not result["findings"]:
            result["findings"].extend(_scan_for_runtime_issues(stdout_text))
        # Check tail
        if output_text and not result["findings"]:
            tail = "\n".join(output_text.splitlines()[-tail_lines:])
            result["findings"].extend(_scan_for_runtime_issues(tail))

        if result["findings"]:
            result["status"] = "failed"
            result["tail_lines_checked"] = tail_lines

    # Generate context-aware suggestions
    result["suggestions"] = _generate_suggestions(result, context or {})
    result["ok"] = result["status"] in ("completed", "unknown")

    return result


def _scan_for_runtime_issues(text: str) -> list[dict]:
    """Scan stderr/stdout for runtime/MPI/MCNP executable issues."""
    findings: list[dict] = []
    patterns = [
        ("MPI_LAUNCHER_NOT_FOUND", "runtime", 1, r"mpirun.*not\s+found|mpiexec.*not\s+found"),
        ("MCNP_EXECUTABLE_NOT_FOUND", "runtime", 1, r"mcnp5.*not\s+found|mcnp6.*not\s+found|command\s+not\s+found"),
        ("RUNTIME_PERMISSION_DENIED", "runtime", 1, r"permission\s+denied|access\s+denied"),
        ("RUNTIME_COMMAND_FAILED", "runtime", 1, r"cannot\s+execute|unable\s+to\s+launch|no\s+such\s+file"),
        ("MPI_PROCESS_FAILED", "runtime", 1, r"process\s+failed"),
    ]
    for line in text.splitlines()[:200]:
        for code, category, priority, pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append({
                    "code": code, "category": category, "priority": priority,
                    "line": 0, "evidence": line.strip()[:200],
                    "match": re.search(pattern, line, re.IGNORECASE).group(0) if re.search(pattern, line, re.IGNORECASE) else "",
                })
                break
    return findings


def _generate_suggestions(result: dict, context: dict) -> list[dict]:
    """Generate context-aware Chinese suggestions from findings and context."""
    suggestions: list[dict] = []
    codes = {f["code"] for f in result["findings"]}
    categories = {f["category"] for f in result["findings"]}
    ss = context.get("source_strategy", "")
    pp = context.get("postprocess", "none")
    model = context.get("model", "")

    # input_format → recommend diagnose-deck / repair-deck
    if "input_format" in categories:
        suggestions.append({
            "action": "run_diagnose_deck",
            "message": "检测到输入格式问题。请运行 diagnose-deck 检查 80 列限制、tab、continuation、comment card 等 MCNP5_RSICC 1.14 规则。",
        })
        suggestions.append({
            "action": "consider_repair_deck",
            "message": "如果只涉及 tab、超长注释、Unicode 标点等安全格式问题，可以运行 repair-deck 自动修复。修复不会改变几何、材料、F card、source physics。",
        })

    # geometry / cell / surface
    if "geometry" in categories:
        suggestions.append({
            "action": "check_cell_surface_cards",
            "message": "检测到 cell/surface 几何问题。请检查 cell boolean expression 中引用的 surface id 是否存在，以及 surface card 是否正确定义。这类问题不能安全自动修复。",
        })

    # material
    if "material" in categories:
        suggestions.append({
            "action": "check_material_xsdir",
            "message": "检测到 material/cross-section 问题。请检查 m card 和 cell 引用的 material id，以及合法 MCNP 截面库/xsdir 配置。本 skill 不提供截面库下载或授权绕过。",
        })

    # source
    if "source" in categories:
        if ss == "disk_tr1":
            suggestions.append({
                "action": "check_disk_tr1_cards",
                "message": "当前使用 disk_tr1 面源策略。请检查生成的 TR/SI/SP/SDEF cards，确认 source_radius、source_card_id 是否冲突或缺失。",
            })
        suggestions.append({
            "action": "check_sdef_cards",
            "message": "请检查 SDEF card 和 SI/SP/TR 定义。不要自动修改 source physics。",
        })

    # tally
    if "tally" in categories:
        if "F8" not in (pp or ""):
            suggestions.append({
                "action": "check_non_f8_tally",
                "message": f"检测到 tally 问题。当前请求 postprocess={pp}。如果 tally 非 F8，可以 run-only / sweep / batch，但不能 CSV/plot。CSV/plot 只支持 F8 pulse-height tally。",
            })

    # mode
    if "mode" in categories:
        suggestions.append({
            "action": "check_mode_card",
            "message": "检测到 MODE/粒子不匹配。请检查 MODE card 是否包含 source 和 tally 所需的粒子类型（p/e/n）。",
        })

    # runtime
    if "runtime" in categories:
        suggestions.append({
            "action": "run_runtime_check",
            "message": "检测到 MPI/MCNP executable 运行时问题。请运行 runtime-check 检查 mpirun/mpiexec 和 mcnp5mpi/mcnp5 是否在 PATH 中。",
        })

    # template model warning
    if "template" in model and ("source" in categories or "geometry" in categories):
        suggestions.append({
            "action": "validate_template_assumptions",
            "message": f"当前模型 {model} 是未验证模板。几何和 reference point 基于模板假设，请用你的 detector datasheet 验证后再分析。",
        })

    # general: run diagnose-deck if errors present
    if result["status"] in ("failed", "error") and "runtime" not in categories:
        if not any(s["action"] == "run_diagnose_deck" for s in suggestions):
            suggestions.append({
                "action": "run_diagnose_deck",
                "message": "建议运行 diagnose-deck 进行 MCNP5_RSICC 1.14 输入格式检查。",
            })

    return suggestions


# ---------------------------------------------------------------------------
# file-level convenience
# ---------------------------------------------------------------------------

def analyze_mcnp_failure_file(
    output_path: str | Path | None = None,
    stdout_path: str | Path | None = None,
    stderr_path: str | Path | None = None,
    context_path: str | Path | None = None,
    mcnp_version: str = "mcnp5_rsicc_1_14",
    front_lines: int = 300,
    tail_lines: int = 120,
) -> dict[str, Any]:
    """Read output/stderr/stdout files and run :func:`analyze_mcnp_failure`."""
    output_text = None
    stdout_text = None
    stderr_text = None
    context = None

    if output_path:
        op = Path(output_path)
        if op.is_file():
            output_text = op.read_text(encoding="utf-8", errors="replace")

    if stdout_path:
        sp = Path(stdout_path)
        if sp.is_file():
            stdout_text = sp.read_text(encoding="utf-8", errors="replace")

    if stderr_path:
        ep = Path(stderr_path)
        if ep.is_file():
            stderr_text = ep.read_text(encoding="utf-8", errors="replace")

    if context_path:
        cp = Path(context_path)
        if cp.is_file():
            import json
            try:
                context = json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                context = None

    return analyze_mcnp_failure(
        output_text=output_text,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        context=context,
        mcnp_version=mcnp_version,
        front_lines=front_lines,
        tail_lines=tail_lines,
    )


def render_failure_response(result: dict[str, Any]) -> str:
    """Render MCNP failure analysis as user-facing Chinese text."""
    lines: list[str] = []
    status = result.get("status", "unknown")

    if status == "completed":
        lines.append("运行看起来正常完成。")
        if result["findings"]:
            lines.append(f"output 中检测到 MCNP version: {result.get('mcnp_version_detected', 'unknown')}")
        return "\n".join(lines)

    if status in ("failed", "error"):
        lines.append("运行没有正常完成。")
    elif status == "warning":
        lines.append("运行完成但存在 warning。")
    else:
        lines.append("无法判断是否正常完成。")

    lines.append("")

    # Analysis scope
    front = result.get("front_lines_analyzed", 0)
    total = result.get("total_output_lines", 0)
    if front > 0:
        lines.append(f"优先检查了 output 前 {front} 行（共 {total} 行）。")
    if result.get("fallback_used"):
        lines.append("output 前部未发现明确错误，已补充查看 stderr/stdout/结尾摘要。")

    lines.append(f"按 MCNP5_RSICC 1.14 保守规则解释。")
    lines.append("")

    # Findings
    findings = result.get("findings", [])
    if findings:
        lines.append("主要发现：")
        cat_names = {
            "fatal": "致命错误", "input_format": "输入格式", "geometry": "几何/surface",
            "material": "材料/截面库", "tally": "Tally", "source": "源项/SDEF",
            "mode": "MODE/粒子", "runtime": "MPI/运行时", "warning": "警告",
            "error": "错误",
        }
        for f in findings:
            code = f.get("code", "")
            cat = f.get("category", "")
            cat_display = cat_names.get(cat, cat)
            ev = f.get("evidence", "")[:120]
            lines.append(f"  [{cat_display}] {code}")
            if ev:
                lines.append(f"    {ev}")
        lines.append("")

    # Suggestions
    suggestions = result.get("suggestions", [])
    if suggestions:
        lines.append("修改建议：")
        for s in suggestions:
            lines.append(f"  - {s.get('message', '')}")
        lines.append("")

    # Context
    ctx = result.get("context", {})
    if ctx:
        model = ctx.get("model", "")
        ss = ctx.get("source_strategy", "")
        pp = ctx.get("postprocess", "none")
        if model:
            lines.append(f"当前模型: {model}")
        if ss:
            lines.append(f"源策略: {ss}")
        if pp and pp != "none":
            lines.append(f"后处理请求: {pp}")

    return "\n".join(lines)
