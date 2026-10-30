"""Translate trace records to public labels only; never forward trace payloads."""

LABELS = {"astro": "西方占星", "bazi": "八字", "tarot": "塔罗", "name": "姓名", "dream": "解梦"}
COMPUTE = {
    "compute_bazi": "正在排八字",
    "compute_bazi_period": "正在推演流期",
    "compute_natal_chart": "正在排星盘",
    "compute_transits": "正在算行运",
    "draw_tarot": "正在抽牌",
    "daily_fortune": "正在推算每日运势",
    "analyze_name": "正在分析姓名",
    "lookup_dream_symbols": "正在分析梦境意象",
}


# The pipeline's own stages (pipeline/runner.py); calculations are labelled from tool_plan.
STAGES = {
    "intent": "正在理解你的问题",
    "resume": "正在接着上次的牌面继续",
    "compose": "正在撰写解读",
    "repair": "事实核对未通过，正在改写",
    "degrade": "正在整理牌面的基础解读",
}


def progress_label(record):
    event = record.get("event")
    if event == "pipeline_stage":
        return STAGES.get(record.get("stage"))
    if event in ("model_response", "tool_plan"):
        names = record.get("tool_names", [])
        for name, label in COMPUTE.items():
            if name in names:
                return label
        if record.get("role") == "orchestrator" and record.get("step") == 0:
            return "正在理解你的问题"
    if event in ("specialist_started", "specialist_finished"):
        label = LABELS.get(record.get("system"), "体系")
        if event == "specialist_started":
            return f"正在请{label}专家推演"
        return f"{label}专家已交报告" if record.get("status") == "ok" else f"{label}专家未完成"
    if event != "tool_result":
        return None
    name = (record.get("call") or {}).get("name")
    result = record.get("result") or {}
    if name == "resolve_location":
        return "正在确认出生地"
    if name == "merge_signals" and result.get("ok"):
        return "正在比对各体系的呼应与分歧"
    if name == "submit_reading":
        if result.get("ok"):
            return "解读已完成"
        if result.get("code") == "validation_failed":
            return "事实核对未通过，正在改写"
        if result.get("code") == "review_revise":
            return "审校提出修改，正在改写"
    return None
