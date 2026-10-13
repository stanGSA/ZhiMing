"""Specialist definitions: prompt, restricted tool table and the profile fields each may see."""

import re
from dataclasses import dataclass

from agents.schemas import ReportInput
from common.schemas import Evidence, Reading, Safety
from harness.registry import Registry, Tool

SHARED_RULES = """你在隔离的子会话中工作：只看得到编排者给的子问题（JSON）和本体系需要的画像字段，看不到其它专家的结果，也不能直接询问用户。
只用本体系工具。出生资料只能来自画像或用户原话；地点只用子问题里的location_id或画像，不能自行填写经纬度、时区、fold、性别或口径。工具返回status=needs_input时停止计算，系统会把问题交给编排者统一追问，不要猜测答案。
要点的ref_id必须逐字使用工具结果interpretations或牌面中的ref_id（不是kb_ref）；每条要点用一句话写清计算事实及其象征主题，不编造落座、宫位、相位、干支、牌面或日期。
answer用一句话回答子问题，给出有条件的倾向和现实前提；不评论其它体系，不写免责声明、审核、知识库或工具等内部信息。释义未人工审核时confidence为low并说明原因。
子问题JSON中existing_results不为空时，表示本记录已完成这些计算（例如已经抽出的牌），直接据此写报告，不要重算或重抽。
计算完成后调用submit_report提交answer、points、missing（不可用或缺失的信息）和confidence；不要输出普通文本。"""

ASTRO_PROMPT = f"""你是知命的西方占星专家。
{SHARED_RULES}
性格、工作方式类用本命盘。子问题带timeframe时，必须用相同起止日期和时区调用compute_transits，不以原局代替行运。
出生时间未知时不解读宫位、上升、天顶，并说明月亮和精确行运日期存在中午代理时间的不确定性。
compute_transits只给出精确相位节点及解释容许度，没有计算持续有效窗口；不把节点扩展成数日的运势窗口。精确相位日期不是录用等现实事件日期，跨时区时区分当地日期与UTC日期。
结合行星落座宫位，以及行运的transit_body/natal_body/aspect解释；theme_map的0是中性方向，不代表正负评价。职业题回答工作方式，具体职业只作待验证的例子。"""

BAZI_PROMPT = f"""你是知命的八字专家。
{SHARED_RULES}
birth_local和tz始终是用户原始出生地的钟表资料，不得先换算成北京时间、UTC或真太阳时再传入，工具内部负责历史夏令时与口径转换。默认zishi_rule=next_day、true_solar_time=false；用户明确要求时按其规则。海外出生须有用户对真太阳时或固定UTC+8口径的确认，工具会据原话核对。
未标注农历时按公历；calendar=lunar须有用户说明，普通月/闰月不明确时工具会要求追问。缺性别仍可算原局，但不排大运。MVP不判喜用神，不把冲合当灾祸，不以五行简单计数判断旺衰。
子问题带timeframe时，必须用相同起止日期和时区调用compute_bazi_period，节气流月按工具给出的实际边界表述，不当成公历整月。大运序列中的start_year只是年份标记，不代表当年已经交运。
原问题要求日主、起运日期或首步大运时，要点中必须写出计算结果。"""

TAROT_PROMPT = f"""你是知命的塔罗专家。
{SHARED_RULES}
每个记录只抽一次：调用一次draw_tarot即可，draw_tarot已返回牌面与精确释义，通常不必再查询。牌阵single=单张，three_card=过去/现在/未来，decision=现状/A/B；子问题给了spread就用它，否则二选一用decision，其余默认three_card。
要点逐张引用牌面ref_id并结合子问题解释，正逆位必须与抽牌结果一致。二选一时answer写“更倾向A/B，前提是…”并说明另一选项的成本；牌面只提供反思线索，不预测结果。"""

NAME_PROMPT = f"""你是知命的姓名五格专家。
{SHARED_RULES}
用analyze_name分析子问题里的名字：姓名必须来自用户原话或画像name，复姓（如欧阳）按复姓拆分；两个名字各调用一次。子问题JSON带bazi_id时可传入，只并列三才五行与原局五行计数。
笔画按康熙字典繁体计，与现代简体笔画不同。工具返回ambiguities时，将confirmation_prompts放进points要点说明默认写法与备选写法的笔画，请用户按证件写法确认，不只放confidence.reason；forms只在用户明确说明写法时填写。
五格数理吉凶是民间约定、各家有分歧：answer写有条件的倾向，不作命运断言，不判喜用神，不建议改名或“补”某个五行。起名与合婚不在本期范围。"""

DREAM_PROMPT = f"""你是知命的解梦专家。
{SHARED_RULES}
从原问题的梦境描述中抽出意象，一次调用lookup_dream_symbols：每项写phrase（逐字摘自用户描述的连续片段）和symbol（规范说法，如“牙齿一颗一颗掉下来”→“掉牙”，“被一条大狗追”→“狗”“被追”；词典外的词照抄原文）；不加入用户没说的内容。
只解读hits里的意象，要点引用其ref_id；misses里的意象写进missing并说明词典未收录、不作解读。梦境只反映心理与情绪，不说预兆、预示或现实中会发生什么；涉及去世的亲人、葬礼、医院时语气温和，不暗示健康或生死。没有任何命中时如实说明，并在missing里请用户补充细节。"""

CONTINUE_PROMPT = "本轮尚未完成。计算完成后请调用 submit_report 提交结构化报告，不要输出普通文本。"

SPEC_CONFIG = {
    "astro": dict(
        label="西方占星",
        prompt=ASTRO_PROMPT,
        temporal=True,
        repeatable=True,
        profile_fields=(
            "birth_local_dt",
            "time_known",
            "birth_place",
            "location_id",
            "tz",
            "lat",
            "lon",
            "consultation_tz",
        ),
    ),
    "bazi": dict(
        label="八字",
        prompt=BAZI_PROMPT,
        temporal=True,
        repeatable=True,
        profile_fields=(
            "birth_local_dt",
            "time_known",
            "birth_place",
            "location_id",
            "tz",
            "lat",
            "lon",
            "consultation_tz",
            "gender",
            "calendar_input",
            "zishi_rule",
            "true_solar_time",
        ),
    ),
    "name": dict(
        label="姓名", prompt=NAME_PROMPT, temporal=False, repeatable=True, profile_fields=("name",)
    ),
    "dream": dict(
        label="解梦", prompt=DREAM_PROMPT, temporal=False, repeatable=True, profile_fields=()
    ),
    # One draw per reading: once tarot has a valid report it is reused, never redrawn.
    "tarot": dict(
        label="塔罗", prompt=TAROT_PROMPT, temporal=False, repeatable=False, profile_fields=()
    ),
}

INTERNAL = re.compile(
    r"active_reading_id|missing_dependency|submit_report|submit_reading|存储错误|保存失败|知识库|未人工审核"
)


@dataclass(frozen=True)
class SpecialistSpec:
    system: str
    label: str
    prompt: str
    temporal: bool
    repeatable: bool
    profile_fields: tuple[str, ...]
    registry: Registry


def as_reading(report: ReportInput, system: str) -> Reading:
    """Shape a report like a Reading so each plugin's existing output checks apply unchanged."""
    return Reading.model_construct(
        question_type="trait",
        systems_used=[system],
        summary=report.answer,
        evidence=[Evidence.model_construct(ref_id=p.ref_id, reading=p.text) for p in report.points],
        resonances=[],
        tensions=[],
        timeline=[],
        advice=[],
        confidence=report.confidence,
        safety=Safety.model_construct(flag=False, note=""),
        followups=list(report.missing),
    )


def validate_report(args: ReportInput, session) -> str | None:
    state = session.state
    own = [s for s in state.get("signals", []) if s["system"] == session.role]
    if not own:
        return "须先调用本体系的计算或抽牌工具，再提交报告"
    refs = {s["ref_id"] for s in own}
    if any(point.ref_id not in refs for point in args.points):
        return "要点ref_id必须来自本体系本次计算的interpretations或牌面ref_id"
    text = " ".join([args.answer, *(p.text for p in args.points), *args.missing])
    if INTERNAL.search(text):
        return "报告不能包含内部状态、审核或存储信息"
    if re.search(r"仅供参考|仅供娱乐|仅供.*反思", text):
        return "报告不要写免责声明"
    validator = session.output_validators.get(session.role)
    if validator:
        error = validator(as_reading(args, session.role), state)
        if error:
            return error
    if state.get("timeframe_required") and SPEC_CONFIG[session.role]["temporal"]:
        if not any(s["horizon"] == "timing" for s in own):
            return "子问题指定了时间范围，须计算本体系行运或流期，不能只用原局"
    if any(not s["reviewed"] for s in own) and args.confidence.level != "low":
        return "释义尚未人工审核，confidence必须为low并说明原因"
    return None


def submit_report(args: ReportInput, session) -> dict:
    session.state["complete"] = True
    return {"text": args.answer, "report": args.model_dump(mode="json")}


def build_specialists(plugins, lookup_tool: Tool) -> dict[str, SpecialistSpec]:
    """One restricted registry per plugin; a plugin without a defined specialist is an error."""
    report_tool = Tool(
        "submit_report",
        "提交本体系的结构化报告：answer一句话回答子问题，points逐条引用本次计算ref_id。",
        ReportInput,
        submit_report,
        roles=frozenset(plugin.name for plugin in plugins),
        dependency="active_reading_id",
        idempotent=False,
        terminal=True,
        validator=validate_report,
    )
    specs = {}
    for plugin in plugins:
        if plugin.name not in SPEC_CONFIG:
            raise ValueError(f"插件 {plugin.name} 缺少专家定义")
        registry = Registry()
        for tool in plugin.tools:
            registry.register(tool)
        registry.register(lookup_tool)
        registry.register(report_tool)
        specs[plugin.name] = SpecialistSpec(
            system=plugin.name, registry=registry, **SPEC_CONFIG[plugin.name]
        )
    return specs
