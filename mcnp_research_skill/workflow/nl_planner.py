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
    nps_match = re.search(
        r"(?:nps|粒子数|源强度|histories|粒子源强度)\s*[=：:\s]*\s*(\d+(?:\.\d+)?(?:[eE]\d+)?)",
        text, re.IGNORECASE,
    )
    if nps_match:
        raw = nps_match.group(1)
        if "e" in raw.lower():
            parts = raw.lower().split("e")
            nps_val = int(float(parts[0]) * (10 ** int(parts[1])))
            if "源强度" in nps_match.group(0):
                warnings.append({
                    "code": "SOURCE_STRENGTH_INTERPRETED_AS_NPS",
                    "message": f"将'源强度 {raw}'解释为 NPS={nps_val}（MCNP histories），非活度 Bq。",
                })
        else:
            fval = float(raw)
            if fval >= 1e4:
                nps_val = int(fval)

    if nps_val is None:
        pow_match = re.search(r"10\s*的\s*(\d+)\s*次方|10\s*\^\s*(\d+)", text)
        if pow_match:
            exp = int(pow_match.group(1) or pow_match.group(2))
            nps_val = 10 ** exp
            warnings.append({
                "code": "SOURCE_STRENGTH_INTERPRETED_AS_NPS",
                "message": f"将'10的{exp}次方'解释为 NPS={nps_val}（MCNP histories）。",
            })

    if nps_val is None:
        hist_match = re.search(
            r"(?:运行粒子数|粒子数|histories|运行粒子)\s*[=：:\s]*\s*(\d+(?:\.\d+)?(?:[eE]\d+)?)",
            text, re.IGNORECASE,
        )
        if hist_match:
            raw = hist_match.group(1)
            if "e" in raw.lower():
                parts = raw.lower().split("e")
                nps_val = int(float(parts[0]) * (10 ** int(parts[1])))
            else:
                nps_val = int(float(raw))

    # "1e7 histories" (number before keyword)
    if nps_val is None:
        num_hist_match = re.search(
            r"(\d+(?:\.\d+)?(?:[eE]\d+)?)\s*histories",
            text, re.IGNORECASE,
        )
        if num_hist_match:
            raw = num_hist_match.group(1)
            if "e" in raw.lower():
                parts = raw.lower().split("e")
                nps_val = int(float(parts[0]) * (10 ** int(parts[1])))
            else:
                nps_val = int(float(raw))

    # ---- detect distances ----
    distances: list[float] | None = None
    start: float | None = None
    stop: float | None = None
    step: float | None = None
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:cm|厘米|公分)?\s*(?:到|至|[-~]|to)\s*(\d+(?:\.\d+)?)\s*(?:cm|厘米|公分)?"
        r".*?(?:每步|步长|step|每间隔)\s*(\d+(?:\.\d+)?)",
        text, re.IGNORECASE,
    )
    if range_match:
        start = float(range_match.group(1))
        stop = float(range_match.group(2))
        step = float(range_match.group(3))
    else:
        list_match = re.search(
            r"(?:距离|distances?)[：:\s]*([\d\s.,]+?)(?:\s*(?:cm|厘米|公分))",
            text, re.IGNORECASE,
        )
        if list_match:
            nums = re.findall(r"(\d+(?:\.\d+)?)", list_match.group(1))
            if nums:
                distances = [float(n) for n in nums]

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

    intent: str = "unknown"
    if re.search(r"sweep|扫描|扫|每隔|每步|step", text, re.IGNORECASE) and re.search(r"距离|distance|\d+\s*cm|\d+\s*厘米", text, re.IGNORECASE):
        intent = "run_sweep" if execute_requested else "prepare_sweep"
    elif re.search(r"检查|diagnos|inspect|是否符合", text, re.IGNORECASE):
        intent = "diagnose_deck"
    elif re.search(r"批量|batch|多.*文件|目录|input.dir", text, re.IGNORECASE):
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
    if source_strategy == "disk_tr1":
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
        "postprocess": postprocess,
        "execute_requested": execute_requested,
        "can_execute_now": can_execute,
        "missing_required": missing,
        "warnings": warnings,
        "errors": errors,
        "runtime_preflight": runtime,
        "cli_preview": cli_preview,
    }
