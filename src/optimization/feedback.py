"""Normalize C's mapped area, pre-mapping LTP depth and optional STA report."""


def _number(value):
    return value if type(value) in (int, float) else None


def _metrics(report):
    if not isinstance(report, dict) or report.get("status") not in (None, "success"):
        return {}
    metrics = {}
    area = _number(report.get("area"))
    if area is not None:
        metrics["area"] = (area, report.get("area_unit"))
    depth = _number(report.get("logic_depth"))
    delay = _number(report.get("delay"))
    unit = report.get("delay_unit")
    if depth is None and unit in (None, "ltp", "levels", "level"):
        depth = delay  # Legacy C evaluator returns a unitless integer LTP count.
    if depth is not None and depth >= 0 and int(depth) == depth:
        metrics["logic_depth"] = (int(depth), "levels")
    if unit in ("ps", "ns", "us") and delay is not None:
        metrics["path_delay"] = (delay, unit)
    # Optional feedback.evaluate.sta contract (no STA tool invocation here):
    # {status, unit: "ps"|"ns"|"us", path_delay, slack, startpoint, endpoint}.
    sta = report.get("sta")
    if isinstance(sta, dict) and sta.get("status") in (None, "success"):
        unit = sta.get("unit")
        if unit in ("ps", "ns", "us"):
            for key in ("path_delay", "slack"):
                value = _number(sta.get(key))
                if value is not None:
                    metrics[key] = (value, unit)
    return metrics


def performance_summary(feedback, context):
    """Compare reports supplied as a pair; reject explicit config/unit mismatches."""
    baseline = feedback.get("baseline") or {}
    current = feedback.get("evaluate") or {}
    before = _metrics(baseline)
    after = _metrics(current)
    comparable = isinstance(baseline, dict) and all(
        baseline.get(key) == current.get(key)
        for key in ("config_id", "config_version", "is_mock")
        if key in baseline or key in current
    )
    metrics = {}
    for key in sorted(before.keys() | after.keys()):
        old, old_unit = before.get(key, (None, None))
        new, new_unit = after.get(key, (None, None))
        delta = None
        if comparable and old is not None and new is not None and old_unit == new_unit:
            delta = new - old
        metrics[key] = dict(baseline=old, baseline_unit=old_unit, candidate=new,
                            unit=new_unit, delta=delta)
    constraints = context.get("constraints")
    constraints = constraints if isinstance(constraints, dict) else {}
    summary = {"metrics": metrics, "delay_limit": constraints.get("delay_limit"),
               "limit_unit": constraints.get("delay_unit"),
               "timing_met": current.get("timing_met") if current.get("status") == "success" else None}
    if summary["limit_unit"] is None and "logic_depth" in after and summary["delay_limit"] is not None:
        summary["limit_unit"] = "levels"
    if "logic_depth" in after and current.get("delay_unit") in (None, "ltp", "level", "levels"):
        # In C's legacy schema timing_met compares LTP to delay_limit, even when
        # a caller accidentally labels that limit as physical time.
        summary["timing_metric"] = "logic_depth"
        if summary["limit_unit"] in ("ps", "ns", "us"):
            summary["timing_met"] = None
    sta = current.get("sta")
    if isinstance(sta, dict) and sta.get("status") in (None, "success") and "slack" in after:
        summary["critical_path"] = {key: sta[key] for key in ("startpoint", "endpoint")
                                    if isinstance(sta.get(key), str)}
    return summary
