"""Deterministic natural-language workflow planner.

Parses Chinese / English natural-language MCNP workflow requests and
produces structured plans with model detection, reference-point
resolution, parameter extraction, and runtime preflight integration.

This is a rule-based parser — no external LLM / API calls.
"""

from __future__ import annotations

import re
from typing import Any

from ..models.registry import get_model, get_model_reference_point, resolve_reference_point_name
from ..mcnp_run.runtime import run_runtime_check

# ---------------------------------------------------------------------------
# model aliases  (detector-size → model_id)
# ---------------------------------------------------------------------------

_MODEL_ALIASES: list[tuple[str, str, bool]] = [
    # (pattern, model_id, is_verified)
    (r"3\s*inch|3\s*英寸|3\s*寸|3\s*x\s*3|3\"|三英寸|三寸|三吋", "nai_3x3_verified", True),
    (r"2\s*inch|2\s*英寸|2\s*寸|2\s*x\s*2|2\"|二英寸|二寸|两英寸|两寸|二吋", "nai_2x2_template", False),
    (r"1\s*inch|1\s*英寸|1\s*寸|1\s*x\s*1|1\"|一英寸|一寸|一吋", "nai_1x1_template", False),
]

# ---------------------------------------------------------------------------
# energy patterns
# ---------------------------------------------------------------------------

_ENERGY_PATTERNS: list[tuple[str, float]] = [
    (r"cs\s*-?\s*137|铯\s*-?\s*137|cesium", 0.662),
    (r"am\s*-?\s*241|镅\s*-?\s*241|americium", 0.0595),
    (r"co\s*-?\s*60|钴\s*-?\s*60|cobalt", 1.25),
    (r"(\d+(?:\.\d+)?)\s*kev", None),  # dynamic: divide by 1000
    (r"(\d+(?:\.\d+)?)\s*mev", None),  # dynamic: use as-is
]

# ---------------------------------------------------------------------------
# source type patterns
# ---------------------------------------------------------------------------

def _detect_source_type(text: str) -> str | None:
    if re.search(r"面源|圆面源|disk\s*source|disk_tr", text, re.IGNORECASE):
        return "disk_tr1"
    if re.search(r"保留源|不改源|existing\s*source|preserve", text, re.IGNORECASE):
        return "preserve_existing_source"
    if re.search(r"点源|point\s*source|point_sdef", text, re.IGNORECASE):
        return "point_sdef_pos"
    return None


# ---------------------------------------------------------------------------
# main planner
# ---------------------------------------------------------------------------

def plan_request(
    text: str,
    *,
    np: int | None = None,
    mpi_launcher: str | None = None,
    mcnp_exe: str | None = None,
) -> dict[str, Any]:
    """Parse a natural-language MCNP workflow request into a structured plan.

    Returns a dict with ``intent``, ``human_summary``, ``workflow_command``,
    parameter mappings, and runtime preflight.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    text_lower = text.lower()

    # ==================================================================
    # Phase 1: extract ALL parameters from text
    # ==================================================================

    # ---- detect NPS ----
    nps_val: int | None = None

    # Patterns ordered from most specific to least
    _SUPERSCRIPT_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

    _NPS_PATTERNS: list[tuple[str, bool]] = [
        # "NPS=1e7", "nps 1e6", "粒子数 1e7", "histories 1e6"
        (r"(?:nps|粒子数|源强度|histories|粒子源强度|运行粒子数|运行粒子)\s*[=：:\s]*\s*(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", False),
        # "1e7 histories" / "1e7 nps" / "1e6 particles" (number before keyword)
        (r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(?:histories|nps|粒子数|运行粒子)", False),
        # "10的7次方粒子数" / "10的6次方" / "10 的 7 次方"
        (r"10\s*的\s*(\d+)\s*次方", True),
        # "10^7粒子数" / "10^6"
        (r"10\s*\^\s*(\d+)", True),
        # "1×10^7" / "1 x 10^7" / "1*10^7"
        (r"(\d+(?:\.\d+)?)\s*[×x\*]\s*10\s*\^\s*(\d+)", True),
        # "1×10⁷" / "10⁶" / "10⁷" (Unicode superscript)
        (r"(\d+(?:\.\d+)?)\s*[×x\*]?\s*10([⁰-⁹]+)", True),
    ]

    for pattern, is_power in _NPS_PATTERNS:
        if nps_val is not None:
            break
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        if is_power:
            # Power/exponent patterns
            if pattern.startswith(r"10\s*的") or pattern.startswith(r"10\s*\^"):
                exp = int(m.group(1))
                base = 1
            elif r"[⁰-⁹]" in pattern:
                # Unicode superscript: translate to ASCII digits
                sup = m.group(2) if len(m.groups()) >= 2 else m.group(1)
                exp = int(sup.translate(_SUPERSCRIPT_MAP))
                base = int(float(m.group(1))) if len(m.groups()) >= 2 else 1
            else:
                # "1×10^7" format
                base = int(float(m.group(1)))
                exp = int(m.group(2))
            nps_val = base * (10 ** exp)
            if "粒子数" in m.group(0) or "运行粒子" in m.group(0) or "NPS" in m.group(0).upper():
                pass  # No warning needed for explicit NPS context
            else:
                warnings.append({
                    "code": "SOURCE_STRENGTH_INTERPRETED_AS_NPS",
                    "message": f"将'{m.group(0)}'解释为 NPS={nps_val}（MCNP histories）。",
                })
        else:
            # Scientific notation or plain number
            raw = m.group(1)
            if re.search(r"[eE]", raw):
                parts = re.split(r"[eE]", raw)
                nps_val = int(float(parts[0]) * (10 ** int(parts[1])))
            else:
                fval = float(raw)
                if fval >= 1e4:
                    nps_val = int(fval)
            if "源强度" in m.group(0):
                warnings.append({
                    "code": "SOURCE_STRENGTH_INTERPRETED_AS_NPS",
                    "message": f"将'源强度 {raw}'解释为 NPS={nps_val}（MCNP histories），非活度 Bq。",
                })

    # ---- detect distances ----
    distances: list[float] | None = None
    start: float | None = None
    stop: float | None = None
    step: float | None = None
    step_warnings: list[dict] = []

    # Unified unit pattern: cm/厘米/公分/mm/毫米 → convert mm to cm
    _UNIT_RE = r"(?:cm|厘米|公分|mm|毫米)"
    _UNIT_FACTOR: dict[str, float] = {"mm": 0.1, "毫米": 0.1}

    def _parse_unit(val: float, unit_raw: str) -> float:
        u = unit_raw.lower().strip()
        return val * _UNIT_FACTOR.get(u, 1.0)

    # Step pattern: flexible Chinese/English step/interval expressions
    # Supports: 每步/步长/每次/每隔/每间隔/间隔/间距/每...运行/每...执行/每...为一次
    _STEP_RE = (
        r"(?:每步|步长(?:为)?|step|每间隔|间隔|间距|每隔|每次(?:\s*前进)?|"
        r"每运行一次前进|每\s*(?:\d+(?:\.\d+)?)\s*" + _UNIT_RE + r"?\s*(?:为一次|运行|执行))"
        r"\s*[=：:\s]*\s*(-?\d+(?:\.\d+)?)\s*(" + _UNIT_RE + r")?"
    )

    # Range: "15-20cm", "15到20厘米", "12.5至16.5cm", "from 15 to 20 cm"
    _RANGE_SEP = r"(?:到|至|[-~—–]|to)"
    _RANGE_RE = (
        r"(?:从|距离\s*从|距离)?"  # optional prefix
        r"(\d+(?:\.\d+)?)\s*(" + _UNIT_RE + r")?\s*"
        + _RANGE_SEP + r"\s*"
        r"(\d+(?:\.\d+)?)\s*(" + _UNIT_RE + r")?"
    )

    # Try range + step combined (single regex)
    range_match = re.search(
        _RANGE_RE + r".*?" + _STEP_RE,
        text, re.IGNORECASE,
    )
    if range_match:
        start = float(range_match.group(1))
        if range_match.group(2):
            start = _parse_unit(start, range_match.group(2))
        stop = float(range_match.group(3))
        if range_match.group(4):
            stop = _parse_unit(stop, range_match.group(4))
        step = float(range_match.group(5))
        if range_match.group(6):
            step = _parse_unit(step, range_match.group(6))

    # Fallback: range only (no step)
    if start is None:
        range_only = re.search(_RANGE_RE, text, re.IGNORECASE)
        if range_only:
            start = float(range_only.group(1))
            if range_only.group(2):
                start = _parse_unit(start, range_only.group(2))
            stop = float(range_only.group(3))
            if range_only.group(4):
                stop = _parse_unit(stop, range_only.group(4))

    # Fallback: step only
    if step is None:
        step_only = re.search(_STEP_RE, text, re.IGNORECASE)
        if step_only:
            step = float(step_only.group(1))
            if step_only.group(2):
                step = _parse_unit(step, step_only.group(2))

    # Fallback: explicit distance list "distances 10 15 20 cm"
    if start is None:
        list_match = re.search(
            r"(?:距离|distances?)[：:\s]*([\d\s.,]+?)(?:\s*(?:" + _UNIT_RE + r"))",
            text, re.IGNORECASE,
        )
        if list_match:
            nums = re.findall(r"(\d+(?:\.\d+)?)", list_match.group(1))
            if nums:
                distances = [float(n) for n in nums]

    # Validate step
    if step is not None and step <= 0:
        errors.append({
            "code": "INVALID_DISTANCE_STEP",
            "message": f"步长/间隔必须为正数，当前值: {step}",
        })
        step = None

    # ---- detect source radius ----
    source_radius: float | None = None
    rad_match = re.search(
        r"(?:半径|radius|source[_ ]radius)\s*[=：:\s]*\s*(\d+(?:\.\d+)?)",
        text, re.IGNORECASE,
    )
    if rad_match:
        source_radius = float(rad_match.group(1))

    # ---- detect source energy ----
    source_energy: float | None = None
    for pat, val in _ENERGY_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if val is not None:
                source_energy = val
            else:
                numeric = float(m.group(1))
                if "kev" in m.group(0).lower():
                    source_energy = numeric / 1000.0
                else:
                    source_energy = numeric
            break

    # ---- detect model ----
    model_id: str | None = None
    model_verified: bool = False
    for pattern, mid, verified in _MODEL_ALIASES:
        if re.search(pattern, text, re.IGNORECASE):
            model_id = mid
            model_verified = verified
            break

    # ---- detect reference point ----
    reference_point_raw: str | None = None
    canonical_rp: str | None = None
    rp_position: list[float] | None = None
    rp_verified: bool = False
    rp_basis: str = ""
    rp_requires_validation: bool = True
    rp_patterns = [
        r"距离(.+?)(?:,|，|\d+|\s*$|到|至|\s+cm|\s+厘米)",
        r"距(.+?)(?:,|，|\d+|\s*$|到|至|\s+cm|\s+厘米)",
        r"from\s+(.+?)(?:,|，|\d+|\s*$|to|\s+cm)",
        r"参考面[：:]\s*(.+?)(?:,|，|\d|$|到|至)",
        r"reference[_\s]point[_\s]?(.+?)(?:,|，|\d|$|to)",
    ]
    for pat in rp_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            reference_point_raw = m.group(1).strip().rstrip("的到至 ,，")
            break

    if reference_point_raw and model_id:
        rp_normalized = reference_point_raw.replace(" ", "_")
        rp_result = get_model_reference_point(model_id, rp_normalized)
        if rp_result is not None and rp_result.get("ok"):
            canonical_rp = rp_result["canonical_name"]
            rp_position = rp_result["position"]
            rp_verified = rp_result["verified"]
            rp_basis = rp_result["basis"]
            rp_requires_validation = rp_result["requires_user_validation"]
        elif rp_result is not None:
            for e in rp_result.get("errors", []):
                errors.append(e)

    # ---- detect source type ----
    source_strategy = _detect_source_type(text)

    # ---- detect postprocess ----
    postprocess = "none"
    _has_plot = bool(re.search(r"画图|绘图|plot|出图|csv.*and.*plot|plot.*and.*csv|csv-and-plot", text, re.IGNORECASE))
    _no_plot = bool(re.search(r"不画图|不绘图|不.*plot|no\s*plot|no_plot", text, re.IGNORECASE))
    _has_csv = bool(re.search(r"csv|只出\s*csv|跑出\s*csv|提取\s*csv", text, re.IGNORECASE))
    _no_csv = bool(re.search(r"不提取\s*csv|不.*csv|no\s*csv|不.*后处理|no\s*postprocess", text, re.IGNORECASE))
    _run_only_sig = bool(re.search(r"只运行|只跑|只批量", text, re.IGNORECASE))

    if _has_plot and not _no_plot:
        postprocess = "csv-and-plot"
    elif _has_csv and not _no_csv:
        postprocess = "csv"
    if _run_only_sig and not _has_plot:
        postprocess = "none"
    if _no_csv and _no_plot:
        postprocess = "none"

    # ---- detect execute intent ----
    execute_requested = bool(re.search(
        r"直接运行|直接跑|直接执行|execute|run\s*now|运行并|跑出|跑并",
        text, re.IGNORECASE,
    ))

    # ==================================================================
    # Phase 2: determine intent from extracted parameters
    # ==================================================================

    # Detect if text implies a distance sweep (range + step, or explicit list)
    _has_sweep_signal = bool(
        re.search(r"sweep|扫描|扫|每隔|每步|step|每次|每间隔|间隔|间距|步长|每\.*运行|每\.*执行", text, re.IGNORECASE)
        or (start is not None and step is not None)  # parsed range + step
        or (distances is not None)  # explicit list
    )
    _has_distance = bool(
        re.search(r"距离|distance|\d+\s*cm|\d+\s*厘米|\d+\s*mm|\d+\s*毫米", text, re.IGNORECASE)
        or start is not None
        or distances is not None
    )
    _is_batch_dir = bool(re.search(r"已有.*txt|批量.*文件|input.dir|目录.*txt|多.*文件.*批量", text, re.IGNORECASE))
    _is_diagnose = bool(re.search(r"检查.*是否符合|diagnos|inspect", text, re.IGNORECASE))

    intent: str = "unknown"
    if _has_sweep_signal and _has_distance:
        intent = "run_sweep" if execute_requested else "prepare_sweep"
    elif _is_diagnose:
        intent = "diagnose_deck"
    elif _is_batch_dir:
        intent = "batch_run_only"
    elif re.search(r"批量|batch", text, re.IGNORECASE) and not _has_sweep_signal:
        intent = "batch_run_only"
    elif re.search(r"后处理|postprocess|提取.*csv|画图", text, re.IGNORECASE):
        intent = "postprocess_only"
    elif re.search(r"运行|run|execute", text, re.IGNORECASE):
        intent = "run_only"
    else:
        intent = "run_only"

    # Early return: model required but not detected
    if model_id is None and intent in ("run_sweep", "prepare_sweep", "run_only"):
        return {
            "ok": False, "status": "needs_clarification", "intent": "unknown",
            "errors": [{"code": "MODEL_NOT_DETECTED",
                "message": "无法从输入中识别探测器型号。请指定 1英寸/2英寸/3英寸 NaI。"}],
            "warnings": warnings,
        }

    model = get_model(model_id) if model_id else None
    requires_user_validation = model.get("requires_user_validation", True) if model else True

    # Check verified-only request
    if model_id and re.search(r"verified|已验证|验证模型|实验验证", text, re.IGNORECASE) and not model_verified:
        errors.append({"code": "MODEL_NOT_VERIFIED",
            "message": f"你要求使用已验证模型，但 {model_id} 是未验证模板。当前只有 nai_3x3_verified 是已验证模型。"})

    # Source strategy default for sweeps
    if source_strategy is None:
        if intent in ("run_sweep", "prepare_sweep") and not re.search(r"保留源|不改源|existing", text, re.IGNORECASE):
            source_strategy = "point_sdef_pos"
            warnings.append({"code": "SOURCE_STRATEGY_ASSUMED_POINT",
                "message": "未指定源类型，sweep 默认使用点源 (point_sdef_pos)。"})

    # Activity check
    if re.search(r"活度|bq|activity|贝克|贝可|Bq", text, re.IGNORECASE):
        errors.append({"code": "ACTIVITY_NORMALIZATION_UNSUPPORTED",
            "message": "活度/activity/Bq 归一化当前不支持。请直接使用 NPS (histories) 指定运行粒子数。"})
    if re.search(r"活度|bq|activity|贝克|贝可|Bq", text, re.IGNORECASE):
        errors.append({
            "code": "ACTIVITY_NORMALIZATION_UNSUPPORTED",
            "message": "活度/activity/Bq 归一化当前不支持。请直接使用 NPS (histories) 指定运行粒子数。",
        })

    # ---- missing required checks ----
    missing: list[str] = []
    if intent in ("run_sweep", "prepare_sweep") and start is None and distances is None:
        missing.append("distance_range")
    if intent in ("run_sweep", "prepare_sweep") and source_energy is None:
        missing.append("source_energy")
    if source_strategy == "disk_tr1" and source_radius is None:
        missing.append("source_radius")

    # ---- determine workflow command ----
    wf_cmd: str = "unknown"
    if intent == "run_sweep":
        wf_cmd = "run-disk-sweep" if source_strategy == "disk_tr1" else "run-point-sweep"
    elif intent == "prepare_sweep":
        wf_cmd = "prepare-disk-sweep" if source_strategy == "disk_tr1" else "prepare-point-sweep"
    elif intent == "diagnose_deck":
        wf_cmd = "diagnose-deck"
    elif intent == "batch_run_only":
        wf_cmd = "batch-workflow"
    elif intent == "run_only":
        wf_cmd = "run-workflow"
    elif intent == "postprocess_only":
        wf_cmd = "postprocess-workflow"

    # ---- runtime preflight ----
    runtime = run_runtime_check(np=np, mpi_launcher=mpi_launcher, mcnp_exe=mcnp_exe)

    # ---- build human summary ----
    model_name = model["display_name"] if model else model_id
    rp_display = canonical_rp or reference_point_raw or "(未指定)"
    dist_display = (
        f"{start}-{stop} cm, 步长 {step} cm" if start is not None
        else f"{distances}" if distances else "(未指定)"
    )
    nps_display = f"{nps_val}" if nps_val else "(未指定)"
    energy_display = f"{source_energy} MeV" if source_energy else "(未指定)"

    human_summary = (
        f"我理解你的任务如下：\n"
        f"- 模型：{model_name}"
        + (f"（已验证）" if model_verified else f"（未验证模板，需要用户验证）") + "\n"
        + (f"- 距离基准：{rp_display}\n" if reference_point_raw else "")
        + f"- 距离：{dist_display}\n"
        + (f"- 源类型：{source_strategy}\n" if source_strategy else "")
        + f"- 源能量：{energy_display}\n"
        + f"- NPS：{nps_display} histories\n"
        + f"- 后处理：{'CSV only' if postprocess == 'csv' else 'CSV + 绘图' if postprocess == 'csv-and-plot' else '无'}\n"
        + f"- 用户请求：{'直接运行' if execute_requested else '仅生成计划/干运行'}"
    )

    confirmation_prompt = (
        "请确认以上理解是否正确。"
        + (" 若正确，使用以下命令进行真实运行。" if execute_requested else "")
    )

    # ---- build CLI preview ----
    cli_preview: list[str] = []
    if wf_cmd not in ("unknown",):
        cli_preview.append(f"python -m mcnp_research_skill.cli {wf_cmd}")
        if model_id:
            cli_preview.append(f"  --builtin-model {model_id}")
        if start is not None:
            cli_preview.append(f"  --start {start} --stop {stop} --step {step}")
        elif distances:
            cli_preview.append(f"  --distances {' '.join(str(d) for d in distances)}")
        if reference_point_raw and rp_position:
            cli_preview.append(f"  --reference-point {canonical_rp}")
        elif rp_position:
            cli_preview.append(f"  --reference-position {rp_position[0]} {rp_position[1]} {rp_position[2]}")
        if source_strategy and source_strategy != "point_sdef_pos":
            cli_preview.append(f"  --source-strategy {source_strategy}")
        if source_energy:
            cli_preview.append(f"  --source-energy {source_energy}")
        if nps_val:
            cli_preview.append(f"  --nps {nps_val}")
        if postprocess != "none":
            cli_preview.append(f"  --postprocess {postprocess}")
        if execute_requested and runtime["can_execute_now"]:
            cli_preview.append(f"  --execute --confirm-mpi --mpi-config cfg.yaml")

    can_execute = (
        runtime["can_execute_now"]
        and not errors
        and len(missing) == 0
        and execute_requested
    )

    return {
        "ok": len(errors) == 0,
        "status": (
            "ready_for_review" if len(errors) == 0 and len(missing) == 0
            else "needs_clarification" if len(errors) > 0
            else "blocked"
        ),
        "intent": intent,
        "human_summary": human_summary,
        "confirmation_prompt": confirmation_prompt,
        "workflow_command": wf_cmd,
        "model": model_id,
        "model_verified": model_verified,
        "requires_user_validation": requires_user_validation,
        "source_strategy": source_strategy,
        "reference_point": reference_point_raw,
        "canonical_reference_point": canonical_rp,
        "reference_position": rp_position,
        "reference_point_verified": rp_verified,
        "reference_point_basis": rp_basis,
        "requires_user_validation_rp": rp_requires_validation,
        "distance": {
            "start": start,
            "stop": stop,
            "step": step,
            "distances": distances,
            "unit": "cm",
        } if (start is not None or distances is not None) else None,
        "nps": nps_val,
        "source_energy": source_energy,
        "source_radius": source_radius,
        "postprocess": postprocess,
        "execute_requested": execute_requested,
        "can_execute_now": can_execute,
        "missing_required": missing,
        "warnings": warnings,
        "errors": errors,
        "runtime_preflight": runtime,
        "cli_preview": cli_preview,
    }
