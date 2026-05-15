"""User-facing Chinese response renderers via codepoint assembly."""
from __future__ import annotations
from typing import Any


def _s(*args: int) -> str:
    """Build a CJK string from Unicode codepoints."""
    return "".join(chr(c) for c in args)


def render_plan_response(result: dict[str, Any]) -> str:
    lines: list[str] = []
    if not result.get("ok") or result.get("status") in ("needs_clarification", "blocked"):
        lines.append(_s(26080,27861,29983,25104,21487,25191,34892,35745,21010,12290))
        for e in result.get("errors", []):
            code = e.get("code", "") if isinstance(e, dict) else ""
            msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
            if code == "MODEL_NOT_DETECTED":
                lines.append(_s(26080,27861,20174,36755,20837,20013,35782,21035,25506,27979,22120,22411,21495,12290,35831,25351,23450,32,49,33521,23544,47,50,33521,23544,47,51,33521,23544,32,78,97,73,12290))
            elif code == "AMBIGUOUS_REFERENCE_POINT":
                lines.append(_s(8220,36317,31163,26230,20307,34920,38754,8221,32,19981,22815,26126,30830,12290))
                lines.append(_s(35831,26126,30830,36873,25321,21442,32771,38754,65306))
                lines.append("  - nai_crystal_front_surface" + _s(65288,30843,21270,38048,26230,20307,21069,34920,38754,65289))
                lines.append("  - nai_crystal_center" + _s(65288,30843,21270,38048,26230,20307,20013,24515,65289))
                lines.append("  - aluminum_shell_front" + _s(65288,38109,22771,34920,38754,65289))
            elif code == "ACTIVITY_NORMALIZATION_UNSUPPORTED":
                lines.append(_s(27963,24230,32,40,66,113,41,19981,33021,30452,25509,24403,20316,78,80,83,32,104,105,115,116,111,114,105,101,115,12290,24403,21069,19981,25903,25345,32,97,99,116,105,118,105,116,121,19968,21270,12290))
            else:
                lines.append(f"({code}) {msg}")
        return "\n".join(lines)
    return _render_plan_ok(result)


def _render_plan_ok(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(_s(25105,29702,35299,20320,30340,38656,27714,26159,65306))
    lines.append("")

    model = result.get("model", "?")
    verified = result.get("model_verified", False)
    display = {
        "nai_3x3_verified": "3x3 NaI(Tl) " + _s(24050,39564,35777,27169,22411),
        "nai_2x2_template": "2x2 NaI(Tl) " + _s(26410,39564,35777,27169,26495),
        "nai_1x1_template": "1x1 NaI(Tl) " + _s(26410,39564,35777,27169,26495),
    }.get(model, model)
    tag = _s(65288,24050,39564,35777,65289) if verified else _s(65288,26410,39564,35777,27169,26495,65292,38656,29992,25143,39564,35777,65289)
    lines.append(f"  {_s(27169,22411)}: {display} {tag}")

    ss = result.get("source_strategy") or "point_sdef_pos"
    ss_map = {"point_sdef_pos": _s(28857,28304), "disk_tr1": _s(22278,38754,28304),
              "preserve_existing_source": _s(20445,30041,28304,39033)}
    lines.append(f"  {_s(28304,31867,22411)}: {ss_map.get(ss, ss)}")

    se = result.get("source_energy")
    if se:
        lines.append(f"  {_s(28304,33021,37327)}: {se} MeV")

    canonical = result.get("canonical_reference_point")
    if canonical:
        rp_map = {"aluminum_shell_front": _s(38109,22771,21069,34920,38754),
                  "nai_crystal_front_surface": _s(30843,21270,38048,26230,20307,21069,31471,34920,38754),
                  "nai_crystal_center": _s(30843,21270,38048,26230,20307,20013,24515)}
        rp_display = rp_map.get(canonical, canonical)
        vt = _s(65288,26469,33258,65,46,116,120,116,39564,35777,20960,20309,65289) if result.get("reference_point_verified") else _s(65288,27169,26495,20551,35774,22352,26631,65292,38656,29992,25143,39564,35777,65289)
        lines.append(f"  {_s(36317,31163,22522,20934)}: {rp_display} {vt}")
        if result.get("reference_position"):
            rp = result["reference_position"]
            lines.append(f"  {_s(21442,32771,22352,26631)}: ({rp[0]}, {rp[1]}, {rp[2]})")

    dist = result.get("distance") or {}
    if dist.get("start") is not None:
        lines.append(f"  {_s(36317,31163)}: {dist['start']}-{dist['stop']} cm, {_s(27493,38271)} {dist['step']} cm")
    elif dist.get("distances"):
        lines.append(f"  {_s(36317,31163)}: {', '.join(str(d) for d in dist['distances'])} cm")

    nps = result.get("nps")
    if nps:
        lines.append(f"  NPS: {nps} histories (MCNP {_s(36816,34892,31890,23376,25968)}, {_s(19981,26159)} Bq {_s(27963,24230)})")

    pp = result.get("postprocess", "none")
    pp_map = {"csv": _s(21482,25552,21462,67,83,86), "csv-and-plot": "CSV + " + _s(32472,22270), "none": _s(19981,21518,22788,29702)}
    lines.append(f"  {_s(21518,22788,29702)}: {pp_map.get(pp, pp)}")

    lines.append("  " + (_s(29992,25143,35831,27714,30452,25509,36816,34892) if result.get("execute_requested") else _s(29992,25143,35831,27714,20165,29983,25104,35745,21010,24178,36816,34892)))

    for w in result.get("warnings", []):
        code = w.get("code", "") if isinstance(w, dict) else ""
        if code == "SOURCE_STRENGTH_INTERPRETED_AS_NPS":
            lines.append(_s(27880,24847,65306,8220,28304,24378,24230,8221,35299,37322,20026,77,67,78,80,104,105,115,116,111,114,105,101,115,65292,19981,26159,66,113,27963,24230,12290))
        elif code == "SOURCE_STRATEGY_ASSUMED_POINT":
            lines.append(_s(27880,24847,65306,40664,35748,28857,28304,40,112,111,105,110,116,95,115,100,101,102,41,12290))

    missing = result.get("missing_required", [])
    if missing:
        lines.append(_s(30446,21069,32570,23569,20197,19979,21442,25968,65306))
        for m in missing:
            if m == "source_energy":
                lines.append("  - " + _s(28304,33021,37327,65306,35831,25351,23450,32,67,115,45,49,51,55,40,48,46,54,54,50,77,101,86,41,12289,65,109,45,50,52,49,40,48,46,48,53,57,53,77,101,86,41,12289,54,54,50,107,101,86,25110,48,46,54,54,50,77,101,86))
            elif m == "source_radius":
                lines.append("  - " + _s(38754,28304,21322,24452,65306,22278,38754,28304,38656,35201,25351,23450,21322,24452))
            elif m == "distance_range":
                lines.append("  - " + _s(36317,31163,33539,22260,65306,35831,25351,23450,115,116,97,114,116,47,115,116,111,112,47,115,116,101,112,25110,100,105,115,116,97,110,99,101,115,21015,34920))
            else:
                lines.append(f"  - {m}")
    elif result.get("execute_requested"):
        lines.append(_s(35831,30830,35748,29702,35299,26159,21542,27491,30830,12290,30830,35748,21518,21487,29992,101,120,101,99,117,116,101,45,112,108,97,110,32,45,45,101,120,101,99,117,116,101,32,45,45,99,111,110,102,105,114,109,45,117,115,101,114,32,30495,23454,36816,34892,12290))
    else:
        lines.append(_s(30830,35748,29702,35299,26080,35823,21518,65292,21487,29992,101,120,101,99,117,116,101,45,112,108,97,110,32,45,45,112,108,97,110,45,102,105,108,101,32,112,108,97,110,46,106,115,111,110,36827,34892,24178,36816,34892,12290))

    return "\n".join(lines)


def render_execute_plan_response(result: dict[str, Any]) -> str:
    lines: list[str] = []
    errors = [e for e in result.get("errors", []) if isinstance(e, dict)]
    if errors:
        for e in errors:
            code = e.get("code", "")
            if code == "USER_CONFIRMATION_REQUIRED":
                lines.append(_s(30495,23454,36816,34892,38656,29992,25143,30830,35748,12290,35831,30830,35748,32,112,108,97,110,7406,35299,27491,30830,21518,65292,21152,19978,45,45,99,111,110,102,105,114,109,45,117,115,101,114,20877,25191,34892,12290))
            elif code == "MCNP_NOT_FOUND":
                lines.append(_s(26410,25214,21040,77,67,78,80,21487,25191,34892,31243,24207,12290))
                lines.append(_s(35831,23433,35013,21512,27861,25480,26435,77,67,78,80,24182,21152,20837,80,65,84,72,65292,25110,20351,29992,45,45,109,99,110,112,45,101,120,101,25351,23450,23436,25972,36335,24452,12290))
                lines.append(_s(26412,115,107,105,108,108,19981,25552,20379,77,67,78,80,19979,36733,12289,23433,35013,25110,25480,26435,32469,36807,12290))
            elif code == "MPI_LAUNCHER_NOT_FOUND":
                lines.append(_s(26410,25214,21040,109,112,105,114,117,110,25110,109,112,105,101,120,101,99,40,77,80,73,108,97,117,110,99,104,101,114,41,12290))
                lines.append(_s(35831,23433,35013,77,80,73,67,72,25110,79,112,101,110,77,80,73,65292,25110,20351,29992,45,45,109,112,105,45,108,97,117,110,99,104,101,114,25351,23450,36335,24452,12290))
            elif code == "PLAN_NOT_EXECUTABLE":
                lines.append(_s(24403,21069,112,108,97,110,29366,24577,19981,21487,25191,34892,65292,35831,35299,20915,38382,39064,21518,20877,35797,12290))
            elif code == "PLAN_MISSING_REQUIRED":
                lines.append("plan " + _s(32570,23569,24517,35201,21442,25968) + ": " + str(e.get("missing", [])))
            else:
                lines.append(f"({code}) {e.get('message', '')}")
        return "\n".join(lines)

    if result.get("dry_run") and not result.get("executed"):
        wf = result.get("workflow_result", {})
        prepared = wf.get("prepared_count", "?")
        lines.append(_s(24050,23436,25104,100,114,121,45,114,117,110,65292,27809,26377,30495,23454,36816,34892,77,67,78,80,47,77,80,73,12290))
        if isinstance(prepared, int) and prepared > 0:
            lines.append(_s(24050,29983,25104) + f" {prepared} " + _s(20010,36317,31163,30340,36755,20837,25991,20214,12290))
        lines.append(_s(26816,26597,26080,35823,21518,21487,29992,45,45,101,120,101,99,117,116,101,32,45,45,99,111,110,102,105,114,109,45,117,115,101,114,30495,23454,36816,34892,12290))
        return "\n".join(lines)

    if result.get("executed"):
        lines.append(_s(24050,25552,20132,30495,23454,36816,34892,12290))
        if result.get("command_preview"):
            lines.append("MPI " + _s(21629,20196) + ": " + result["command_preview"])
        return "\n".join(lines)

    return "OK"


def render_runtime_check_response(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lp = result.get("logical_processors", "?")
    nv = result.get("recommended_np", "?")
    policy = result.get("np_policy", "")
    pn = _s(65288,97,117,116,111,46,112,121,20860,23481,31574,30053,65306,36923,36753,22788,29702,22120,25968,43,49,65292,19981,26159,77,80,73,26631,20934,65289) if policy == "logical_processors_plus_one" else _s(65288,29992,25143,25351,23450,65289)
    lines.append(_s(36923,36753,22788,29702,22120,25968,37327) + ": " + str(lp))
    lines.append(_s(25512,33616,77,80,73,36827,31243,25968) + ": " + str(nv) + " " + pn)
    mpi = result.get("mpi_launcher", {})
    if mpi.get("found"):
        lines.append("MPI launcher: " + _s(24050,25214,21040) + " (" + str(mpi.get("command")) + ", " + _s(36335,24452) + " " + str(mpi.get("path")) + ")")
    else:
        lines.append("MPI launcher: " + _s(26410,25214,21040,109,112,105,114,117,110,25110,109,112,105,101,120,101,99,12290,35831,23433,35013,77,80,73,67,72,25110,79,112,101,110,77,80,73,12290))
    mcnp = result.get("mcnp_executable", {})
    if mcnp.get("found"):
        lines.append("MCNP executable: " + _s(24050,25214,21040) + " (" + str(mcnp.get("command")) + ", " + _s(36335,24452) + " " + str(mcnp.get("path")) + ")")
    else:
        lines.append("MCNP executable: " + _s(26410,25214,21040,109,99,110,112,53,109,112,105,47,109,99,110,112,53,47,109,99,110,112,54,47,109,99,110,112,12290,35831,23433,35013,21512,27861,25480,26435,77,67,78,80,24182,21152,20837,80,65,84,72,12290))
    preview = result.get("command_preview")
    if preview:
        lines.append(_s(25512,33616,21629,20196) + ": " + preview)
    if result.get("can_execute_now"):
        lines.append(_s(24403,21069,29615,22659,21487,20197,36816,34892,77,67,78,80,47,77,80,73,12290))
    else:
        lines.append(_s(24403,21069,29615,22659,26242,19981,20855,22791,30452,25509,36816,34892,26465,20214,12290))
    return "\n".join(lines)


def render_diagnostics_response(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(_s(25353,77,67,78,80,53,95,82,83,73,67,67,49,46,49,52,20445,23432,36755,20837,35268,21017,26816,26597,23436,25104,12290))
    s = result.get("summary", {})
    lines.append(_s(24635,35745) + " " + str(s.get("total", 0)) + " " + _s(39033,38382,39064) + ": blocking=" + str(s.get("blocking", 0)) + " error=" + str(s.get("errors", 0)) + " warning=" + str(s.get("warnings", 0)) + " " + _s(21487,33258,21160,20462,22797) + "=" + str(s.get("fixable", 0)))
    issues = result.get("issues", [])
    if not issues:
        lines.append(_s(26410,26816,27979,21040,38382,39064,12290,35813,36755,20837,25991,20214,31526,21512,77,67,78,80,53,95,82,83,73,67,67,49,46,49,52,20445,23432,35201,27714,12290))
        return "\n".join(lines)
    sz_map = {"blocking": _s(38459,22622), "error": _s(38169,35823), "warning": _s(35686,21578)}
    for i, iss in enumerate(issues, 1):
        code = iss.get("code", "")
        sev = iss.get("severity", "")
        ln = iss.get("line", 0)
        sz = sz_map.get(sev, sev)
        lines.append(f"--- {_s(38382,39064)} {i} [{sz}] {code} ---")
        if ln > 0:
            lines.append("  " + _s(34892,21495) + ": " + str(ln))
        lines.append("  " + str(iss.get("user_explanation", iss.get("observed", ""))))
        if iss.get("auto_fixable"):
            lines.append("  " + _s(21487,33258,21160,20462,22797) + ": " + str(iss.get("suggested_fix", "")))
        else:
            lines.append("  " + _s(38656,25163,21160,22788,29702) + ": " + str(iss.get("suggested_fix", "")))
        lines.append("")
    return "\n".join(lines)


def render_repair_response(result: dict[str, Any]) -> str:
    lines: list[str] = []
    count = result.get("change_count", 0)
    if count > 0:
        lines.append(_s(24050,33258,21160,20462,22797) + " " + str(count) + " " + _s(22788,38382,39064,12290))
        for cl in result.get("change_log", []):
            lines.append("  " + _s(31532) + str(cl.get("line", "?")) + " " + _s(34892) + ": " + str(cl.get("reason", "")))
    else:
        lines.append(_s(27809,26377,25191,34892,33258,21160,20462,22797,12290))
    unfixable = result.get("unfixable_issues", [])
    if unfixable:
        lines.append(str(len(unfixable)) + _s(39033,38382,39064,26080,27861,33258,21160,20462,22797,65306))
        for iss in unfixable:
            lines.append("  " + _s(31532) + str(iss.get("line", 0)) + " " + _s(34892) + " [" + str(iss.get("code", "")) + "]: " + str(iss.get("suggested_fix", "")))
        lines.append(_s(19981,33258,21160,20462,22797,21407,22240,65306,28041,21450,20960,20309,24067,23572,34920,36798,24335,12289,70,99,97,114,100,12289,109,97,116,101,114,105,97,108,12289,115,111,117,114,99,101,112,104,121,115,105,99,115,65292,19981,33021,33258,21160,20462,25913,12290))
    output = result.get("output_path", "")
    if output:
        lines.append(_s(20462,22797,21518,25991,20214,24050,20889,20837) + ": " + output)
    return "\n".join(lines)


def render_non_f8_response(tally_kind: str, postprocess_requested: str) -> str:
    return "\n".join([
        _s(26816,27979,21040,36825,20010,25991,20214,20351,29992,30340,26159) + " " + tally_kind + " tally" + _s(12290),
        "",
        _s(24403,21069,115,107,105,108,108,21487,20197,32487,32493,29983,25104,19981,21516,36317,31163,12289,28304,39033,12289,78,80,83,36755,20837,25991,20214,65292),
        _s(20063,21487,20197,25209,37327,36816,34892,77,67,78,80,65288,114,117,110,45,111,110,108,121,65289,65292),
        _s(20294,67,83,86,47,112,108,111,116,21518,22788,29702,30446,21069,21482,25903,25345,70,56,112,117,108,115,101,45,104,101,105,103,104,116,116,97,108,108,121,12290),
        "",
        _s(24403,21069,35831,27714,30340,21518,22788,29702) + ": " + postprocess_requested,
        _s(8594,22240,20026,38750,70,56,65292,35813,35831,27714,34987,38459,22622,12290),
        "",
        _s(36825,19981,24433,21709,77,67,78,80,36816,34892,33021,21147,12290,20320,21487,20197,65306),
        "  1. " + _s(25913,20026,114,117,110,45,111,110,108,121,40,45,45,112,111,115,116,112,114,111,99,101,115,115,110,111,110,101,41,65292,27491,24120,29983,25104,36755,20837,25991,20214,24182,36816,34892),
        "  2. " + _s(20462,25913,36755,20837,25991,20214,65292,20351,29992,70,56,112,117,108,115,101,45,104,101,105,103,104,116,116,97,108,108,121),
        "  3. " + _s(31561,24453,21518,32493,23454,29616,38750,70,56,101,120,116,114,97,99,116,111,114,65288,70,52,47,70,53,47,70,54,47,70,77,69,83,72,65289),
    ])


def render_non_f8_run_only(tally_kind: str) -> str:
    return _s(26816,27979,21040) + " " + tally_kind + " " + _s(31561,38750,70,56,116,97,108,108,121,12290,24403,21069,23558,25353,114,117,110,45,111,110,108,121,47,112,114,101,112,97,114,101,45,111,110,108,121,32487,32493,65307,19981,20250,36827,34892,67,83,86,47,112,108,111,116,21518,22788,29702,12290)


def render_geb_fit_response(result: dict) -> str:
    lines = []
    used = len(result.get("used_files", []))
    accept = result.get("accepted_count", 0)
    reject = result.get("rejected_count", 0)
    params = result.get("fitted_params") or {}
    geb_ok = result.get("geb_fit_ok", False)

    if geb_ok:
        lines.append(f"From {used} SPE files, extracted peak energies and FWHM.")
        lines.append(f"Accepted: {accept} peaks, Rejected: {reject} peaks.")
        lines.append(f"Fitted GEB parameters: A={params.get('A', 0):.6f}, B={params.get('B', 0):.6f}, C={params.get('C', 0):.6f}")
        lines.append("Review fit quality before writing to MCNP input deck.")
    else:
        lines.append(f"Insufficient valid peaks: {accept} accepted, need at least 3.")
        lines.append("Provide more SPE files or manually specify peak energies/ROI.")
    return "\n".join(lines)


def render_geb_patch_response(result: dict) -> str:
    lines = []
    pr = result.get("patch_result", {})
    if pr.get("ok"):
        pt = pr.get("patches", [{}])[0] if pr.get("patches") else {}
        lines.append(f"FT8 GEB updated: {pt.get('after', '')}")
        outp = result.get("output_path", result.get("patched_deck_path", "output deck"))
        lines.append(f"Original input not overwritten; patched to: {outp}")
    else:
        errs = pr.get("errors", result.get("errors", []))
        for e in errs:
            code = e.get("code", "") if isinstance(e, dict) else ""
            if code == "GEB_REQUIRES_F8":
                lines.append("Current deck has no F8 tally; cannot write FT8 GEB.")
                lines.append("GEB only applies to F8 pulse-height tally.")
                lines.append("Non-F8 decks can still run-only, but GEB energy broadening is not applicable.")
            else:
                msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
                lines.append(f"GEB patch blocked: {msg}")
    return "\n".join(lines)
