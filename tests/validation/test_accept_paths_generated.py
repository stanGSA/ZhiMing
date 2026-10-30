"""Accept paths generated from real calculations (P0.2 of docs/根因整改实施计划.md).

Every sentence below states a fact of this reading's own calculation, phrased the way a correct
answer may phrase it, and the output validators must accept it. A wrong answer that rejects a
correct reading costs a retry, and P1 showed those retries ending in step limits. The sentences
are built from the calculation results, never typed in, so a change to a calculator or a
validator is checked against what the code actually computed.

The mutations change one fact and must be rejected. Wrong facts the validators let through
today are listed as strict xfails: the pipeline's closed-vocabulary check is meant to catch
them, and a fix flips the xfail into a failure that asks for the mark to be removed.
"""

from dataclasses import dataclass

import pytest

from common.schemas import Reading
from common.validation import validate_reading
from plugins.astro.calculator import BODY_ZH, SIGN_ZH, SIGNS
from tests.plugins.test_astro_bazi_integration import invoke, prepare
from tests.plugins.test_name_dream_daily import LOW, ask, with_birth

RANGE = ("2027-02-05", "2027-03-31")
QUESTION = f"看看{RANGE[0]}至{RANGE[1]}的事业运势"
ASPECT_ZH = {
    "conjunction": "合相",
    "opposition": "对分相",
    "square": "四分相",
    "trine": "三分相",
    "sextile": "六分相",
}
PILLAR_ZH = {"year": "年柱", "month": "月柱", "day": "日柱", "time": "时柱"}
FLOW_ZH = {"year": "流年", "month": "流月"}
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]
TEN_GODS = ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印")
CHINESE = "零一二三四五六七八九十"


def chinese(number: int) -> str:
    return CHINESE[number] if number <= 10 else "十" + CHINESE[number - 10]


def orientation(card) -> str:
    return "逆位" if card["reversed"] else "正位"


def opposite(card) -> str:
    return "正位" if card["reversed"] else "逆位"


def layered(session, question_type, body, refs, summary="整体倾向平稳，可以按计划推进。"):
    """A reading whose one section states ``body`` and cites ``refs``."""
    return Reading.model_validate(
        dict(
            question_type=question_type,
            systems_used=sorted({s["system"] for s in session.state["signals"]}),
            summary=summary,
            sections=[dict(title="这一层对你意味着什么", body=body, ref_ids=list(refs))],
            evidence=[dict(ref_id=refs[0])],
            advice=["先做小范围尝试：确认条件后再推进。"],
            confidence=LOW,
            safety=dict(flag=False, note=""),
        )
    )


def ref(session, *parts) -> str:
    """The one citable reference whose identifier contains every part."""
    found = [r for r in session.state["allowed_refs"] if all(p in r for p in parts)]
    assert len(found) == 1, (parts, found)
    return found[0]


def rejections(session, question_type, sentences):
    """(sentence, error) for every sentence the validators refuse."""
    refused = []
    for body, refs in sentences:
        error = validate_reading(layered(session, question_type, body, refs), session)
        if error:
            refused.append((body, str(error)))
    return refused


def unused_jiazi(session) -> str:
    text = repr(session.state)
    return next(gz for gz in JIAZI if gz not in text)


@dataclass
class Charts:
    runtime: object
    natal: dict
    period: dict
    chart: dict
    transits: dict

    @property
    def session(self):
        return self.runtime.session


@pytest.fixture
async def charts(runtime):
    """Bazi with flow months and a natal chart with transits, for one question and range."""
    birth = await prepare(runtime)
    natal = await invoke(runtime, "compute_bazi", {**birth, "gender": "male"})
    runtime.session.append_user(QUESTION + "。")
    runtime.session.state["question"] = QUESTION
    period = await invoke(
        runtime,
        "compute_bazi_period",
        dict(
            bazi_id=natal.data["bazi_id"],
            start=RANGE[0],
            end=RANGE[1],
            granularity="month",
            tz="Asia/Shanghai",
        ),
    )
    chart = await invoke(runtime, "compute_natal_chart", birth)
    transits = await invoke(
        runtime,
        "compute_transits",
        dict(chart_id=chart.data["chart_id"], start=RANGE[0], end=RANGE[1], tz="Asia/Shanghai"),
    )
    assert natal.ok and period.ok and chart.ok and transits.ok
    return Charts(runtime, natal.data, period.data, chart.data, transits.data)


@pytest.fixture
async def tarot(runtime):
    await ask(runtime, "抽三张牌看看近期事业。")
    drawn = await invoke(runtime, "draw_tarot", dict(spread="three_card", question="近期事业"))
    assert drawn.ok
    return drawn.data["cards"]


@pytest.fixture
async def daily(runtime):
    runtime.session.calendar_anchor = "2026-10-30"
    with_birth(runtime)
    await ask(runtime, "今天运势怎么样？")
    result = await invoke(runtime, "daily_fortune", dict(date="2026-10-30"))
    assert result.ok
    return result.data


@pytest.fixture
async def name(runtime):
    await ask(runtime, "帮我看看“欧阳子涵”这个名字")
    result = await invoke(runtime, "analyze_name", dict(surname="欧阳", given="子涵"))
    assert result.ok
    return result.data


@pytest.fixture
async def dream(runtime):
    await ask(runtime, "梦到牙齿一颗一颗掉下来，还梦见在考试")
    result = await invoke(
        runtime,
        "lookup_dream_symbols",
        dict(
            symbols=[
                dict(phrase="牙齿一颗一颗掉下来", symbol="掉牙"),
                dict(phrase="考试", symbol="考试"),
            ]
        ),
    )
    assert result.ok and not result.data["misses"]
    return result.data


# ---- generated accept paths ---------------------------------------------------------------


def bazi_sentences(c: Charts):
    s, natal = c.session, c.natal
    pillars, gods = natal["pillars"], natal["ten_gods_stems"]
    out = [(f"你的日主是{natal['day_master']}，做事讲究分寸。", [ref(s, ":day_master:")])]
    for key, label in PILLAR_ZH.items():
        out.append(
            (f"{label}{pillars[key]}提示了这一层的底色。", [ref(s, f":{key}:{pillars[key]}:gan")])
        )
    out.append(
        (
            f"四柱分别是{pillars['year']}、{pillars['month']}、{pillars['day']}、{pillars['time']}。",
            [ref(s, f":{key}:{pillars[key]}:gan") for key in PILLAR_ZH],
        )
    )
    for key, god in gods.items():
        if key in PILLAR_ZH and key != "day" and god:
            out.append(
                (
                    f"{PILLAR_ZH[key]}天干{pillars[key][0]}是{god}，往往意味着相应的助力。",
                    [ref(s, f":{key}:{pillars[key]}:{god}")],
                )
            )
    dayun = ref(s, ":dayun:")
    first_date, first = dayun.split(":")[-2:]
    out.append((f"{first_date}起运，首步大运{first}。", [dayun]))
    for period in c.period["periods"]:
        start = period["start_utc"]
        for key, gz in period["pillars"].items():
            god = period["ten_gods"][key]
            label = FLOW_ZH[key]
            out.append(
                (f"这段时间{label}{gz}，十神为{god}。", [ref(s, f"{start}:{key}:{gz}:{god}")])
            )
            for relation in period["relations"][key]:
                kind, natal_key = relation["type"], relation["natal_pillar"]
                cited = [ref(s, f"{start}:{key}:{gz}:{kind}:{natal_key}")]
                natal_label = PILLAR_ZH[natal_key] + relation["natal_ganzhi"]
                out.append((f"{label}{gz}与{natal_label}{kind}，节奏容易被打乱。", cited))
                out.append((f"{label}{gz}{kind[-1]}{natal_label}，需要留出缓冲。", cited))
    return out


def astro_sentences(c: Charts):
    s = c.session
    signs = dict(zip(SIGNS, SIGN_ZH, strict=True))
    out = []
    for planet in c.chart["planets"]:
        body, zh = planet["body"], BODY_ZH[planet["body"]]
        sign = ref(s, f":{body}:{planet['sign']}")
        house = ref(s, f":{body}:house{planet['house']}")
        out.append((f"本命{zh}落在{signs[planet['sign']]}座，表达方式更有这一面的风格。", [sign]))
        out.append((f"{zh}{signs[planet['sign']]}让你更看重这一面。", [sign]))
        out.append((f"本命{zh}落在第{planet['house']}宫，相关领域更受关注。", [house]))
        out.append((f"{zh}在{chinese(planet['house'])}宫，提示你在这方面投入较多。", [house]))
    for index, aspect in enumerate(c.chart["aspects"]):
        a, b, kind = BODY_ZH[aspect["a"]], BODY_ZH[aspect["b"]], ASPECT_ZH[aspect["type"]]
        cited = [ref(s, f":natal_aspect{index}:{aspect['a']}:{aspect['b']}:")]
        out.append((f"本命{a}与{b}形成{kind}，内在会有拉扯。", cited))
        out.append((f"{a}{kind[:-1]}{b}，需要学会平衡。", cited))
    for event in c.transits["events"][:20]:
        t, n = BODY_ZH[event["transit_body"]], BODY_ZH[event["natal_body"]]
        kind = ASPECT_ZH[event["aspect"]]
        cited = [ref(s, f"transit:{event['exact_utc']}:{event['transit_body']}:")]
        month, day = int(event["exact_date"][5:7]), int(event["exact_date"][8:10])
        out.append((f"{month}月{day}日前后，行运{t}与本命{n}形成{kind}，适合留意相关安排。", cited))
        out.append(
            (f"行运{t}{kind}本命{n}（精确在{event['exact_date']}），提醒你调整节奏。", cited)
        )
    return out


async def test_bazi_facts_stated_correctly_are_accepted(charts):
    sentences = bazi_sentences(charts)
    assert len(sentences) > 20
    assert rejections(charts.session, "timing", sentences) == []


async def test_astro_facts_stated_correctly_are_accepted(charts):
    sentences = astro_sentences(charts)
    assert len(sentences) > 60
    assert rejections(charts.session, "timing", sentences) == []


async def test_mixed_natal_and_transit_paragraph_is_accepted(charts):
    s, aspect, event = charts.session, charts.chart["aspects"][0], charts.transits["events"][0]
    natal_ref = ref(s, f":natal_aspect0:{aspect['a']}:{aspect['b']}:")
    transit_ref = ref(s, f"transit:{event['exact_utc']}:{event['transit_body']}:")
    body = (
        f"本命{BODY_ZH[aspect['a']]}与{BODY_ZH[aspect['b']]}形成{ASPECT_ZH[aspect['type']]}。"
        f"这个阶段行运{BODY_ZH[event['transit_body']]}与本命{BODY_ZH[event['natal_body']]}"
        f"形成{ASPECT_ZH[event['aspect']]}，外部节奏会推动你调整。"
    )
    assert rejections(s, "timing", [(body, [natal_ref, transit_ref])]) == []


async def test_negated_wrong_values_are_accepted(charts):
    s, natal = charts.session, charts.natal
    other = next(stem for stem in STEMS if stem != natal["day_master"][0])
    sun = next(p for p in charts.chart["planets"] if p["body"] == "Sun")
    elsewhere = next(zh for key, zh in zip(SIGNS, SIGN_ZH, strict=True) if key != sun["sign"])
    sentences = [
        (f"你的日主是{natal['day_master']}，不是{other}。", [ref(s, ":day_master:")]),
        (
            f"太阳在{SIGN_ZH[SIGNS.index(sun['sign'])]}座，不在{elsewhere}座。",
            [ref(s, f":Sun:{sun['sign']}")],
        ),
    ]
    assert rejections(s, "timing", sentences) == []


async def test_negated_sign_before_the_actual_sign_is_accepted(charts):
    s = charts.session
    sun = next(p for p in charts.chart["planets"] if p["body"] == "Sun")
    actual = SIGN_ZH[SIGNS.index(sun["sign"])]
    elsewhere = next(zh for zh in SIGN_ZH if zh != actual)
    sentences = [
        (f"太阳不在{elsewhere}座。", [ref(s, f":Sun:{sun['sign']}")]),
        (f"你的太阳不在{elsewhere}座，而在{actual}座。", [ref(s, f":Sun:{sun['sign']}")]),
        (
            f"太阳不在第{wrong_house(sun)}宫，而在第{sun['house']}宫。",
            [ref(s, f":Sun:house{sun['house']}")],
        ),
    ]
    assert rejections(s, "timing", sentences) == []


async def test_tarot_cards_stated_correctly_are_accepted(runtime, tarot):
    first, second, third = tarot
    refs = [card["ref_id"] for card in tarot]
    positions = "，".join(f"{card['label']}位是{card['name']}{orientation(card)}" for card in tarot)
    sentences = [
        (positions + "。", refs),
        (f"【{second['name']}】{orientation(second)}提示你先稳住。", [refs[1]]),
        (f"现在位置抽到{second['name']}（{orientation(second)}），提示你先稳住。", [refs[1]]),
        (f"第二张牌{second['name']}{orientation(second)}落在现在位置。", [refs[1]]),
        (f"{second['name']}提示你先稳住，再看机会。", [refs[1]]),
        (
            f"{first['name']}{orientation(first)}之后是{third['name']}{orientation(third)}。",
            [refs[0], refs[2]],
        ),
    ]
    assert rejections(runtime.session, "tarot", sentences) == []


async def test_tarot_negated_other_orientation_is_accepted(runtime, tarot):
    card = tarot[1]
    body = f"这次抽到的是{card['name']}{orientation(card)}，不是{card['name']}{opposite(card)}。"
    assert rejections(runtime.session, "tarot", [(body, [card["ref_id"]])]) == []


async def test_tarot_definition_followed_by_draw_clause_is_accepted(runtime, tarot):
    card = tarot[1]
    body = (
        f"本次{card['name']}是{orientation(card)}。"
        f"{card['name']}{opposite(card)}一般表示阻滞，这次不是这种情况。"
    )
    assert rejections(runtime.session, "tarot", [(body, [card["ref_id"]])]) == []


async def test_daily_facts_stated_correctly_are_accepted(runtime, daily):
    s, day, card = runtime.session, daily["day"], daily["card"]
    first, last = day["segments"][0], day["segments"][-1]
    day_ref = ref(s, f"{first['start_utc']}:{day['pillar']}:{day['ten_god']}")
    sentences = [
        (f"今天流日{day['pillar']}，十神为{day['ten_god']}。", [day_ref]),
        (f"今天是{day['pillar']}日，{day['ten_god']}当值。", [day_ref]),
        (f"今天的提示牌是{card['name']}{orientation(card)}。", [card["ref_id"]]),
        (f"今天五行属{day['element']}，适合按自己的节奏推进。", [ref(s, ":day_element:")]),
    ]
    if last is not first:
        late = ref(s, f"{last['start_utc']}:{last['pillar']}:{last['ten_god']}")
        sentences.append((f"晚上11点后进入{last['pillar']}，{last['ten_god']}当令。", [late]))
    for relation in day["relations"]:
        kind, natal_key = relation["type"], relation["natal_pillar"]
        cited = [ref(s, f"{first['start_utc']}:{day['pillar']}:{kind}:{natal_key}")]
        natal = PILLAR_ZH[natal_key] + relation["natal_ganzhi"]
        sentences.append((f"流日{day['pillar']}与{natal}{kind}。", cited))
    assert rejections(s, "daily", sentences) == []


async def test_name_facts_stated_correctly_are_accepted(runtime, name):
    s, grids, sancai = runtime.session, name["grids"], name["sancai"]
    person = ref(s, f":人格:{grids['人格']}")
    listed = "、".join(f"{key}{value}" for key, value in grids.items())
    sentences = [
        (f"欧阳子涵{listed}。", [person]),
        (f"人格数为{grids['人格']}，传统说法里有相应含义。", [person]),
        (f"人格是{grids['人格']}画。", [person]),
        (f"三才配置为{sancai['key']}。", [ref(s, f":三才:{sancai['key']}")]),
    ]
    assert rejections(s, "name", sentences) == []


async def test_dream_symbols_stated_correctly_are_accepted(runtime, dream):
    s = runtime.session
    teeth, exam = ref(s, ":掉牙"), ref(s, ":考试")
    sentences = [
        ("梦见掉牙常和担心失去掌控有关；梦见考试多与被评价的压力相连。", [teeth, exam]),
        ("“牙齿一颗一颗掉下来”这个画面常和焦虑有关。", [teeth]),
    ]
    assert rejections(s, "dream", sentences) == []


# ---- mutations that must be rejected --------------------------------------------------------


def wrong_house(planet) -> int:
    return (planet["house"] + 5) % 12 + 1


def flow_month_ref(c: Charts) -> str:
    period = c.period["periods"][0]
    gz, god = period["pillars"]["month"], period["ten_gods"]["month"]
    return ref(c.session, f"{period['start_utc']}:month:{gz}:{god}")


def transit_sentence(c: Charts, days_late: int, separator: str):
    event = c.transits["events"][0]
    month, day = int(event["exact_date"][5:7]), int(event["exact_date"][8:10]) + days_late
    body = (
        f"{month}月{day}日前后{separator}行运{BODY_ZH[event['transit_body']]}与本命"
        f"{BODY_ZH[event['natal_body']]}形成{ASPECT_ZH[event['aspect']]}。"
    )
    return body, [ref(c.session, f"transit:{event['exact_utc']}:")]


CHART_MUTATIONS = {
    "day_pillar": lambda c: (
        f"日柱{unused_jiazi(c.session)}提示了底色。",
        [ref(c.session, f":day:{c.natal['pillars']['day']}:gan")],
    ),
    "flow_month_ganzhi": lambda c: (
        f"这段时间流月{unused_jiazi(c.session)}。",
        [flow_month_ref(c)],
    ),
    "flow_month_called_flow_year": lambda c: (
        f"流年{c.period['periods'][0]['pillars']['month']}带来新的表达欲。",
        [flow_month_ref(c)],
    ),
    "sun_sign": lambda c: (
        "本命太阳落在"
        + next(
            zh
            for key, zh in zip(SIGNS, SIGN_ZH, strict=True)
            if key != next(p for p in c.chart["planets"] if p["body"] == "Sun")["sign"]
        )
        + "座。",
        [ref(c.session, ":Sun:house")],
    ),
    "sun_house": lambda c: (
        f"本命太阳落在第{wrong_house(next(p for p in c.chart['planets'] if p['body'] == 'Sun'))}宫。",
        [ref(c.session, ":Sun:house")],
    ),
    "natal_aspect_kind": lambda c: (
        f"本命{BODY_ZH[c.chart['aspects'][0]['a']]}与{BODY_ZH[c.chart['aspects'][0]['b']]}"
        + ("对分相。" if c.chart["aspects"][0]["type"] != "opposition" else "合相。"),
        [ref(c.session, ":natal_aspect0:")],
    ),
    "transit_date": lambda c: transit_sentence(c, 4, ""),
    "transit_aspect_kind": lambda c: (
        f"行运{BODY_ZH[c.transits['events'][0]['transit_body']]}与本命"
        f"{BODY_ZH[c.transits['events'][0]['natal_body']]}"
        + ("形成三分相。" if c.transits["events"][0]["aspect"] != "trine" else "形成四分相。"),
        [ref(c.session, f"transit:{c.transits['events'][0]['exact_utc']}:")],
    ),
}

# Wrong facts the validators let through today; the pipeline's closed-vocabulary check
# (docs/根因整改实施计划.md §3.3) is where they are meant to be caught.
CHART_MISSED = {
    "day_master": lambda c: (
        "你的日主是"
        + next(stem for stem in STEMS if stem != c.natal["day_master"][0])
        + "金，做事果断。",
        [ref(c.session, ":day_master:")],
    ),
    "natal_ten_god": lambda c: (
        f"月柱{c.natal['pillars']['month']}为"
        + next(g for g in TEN_GODS if g != c.natal["ten_gods_stems"]["month"])
        + "。",
        [ref(c.session, f":month:{c.natal['pillars']['month']}:gan")],
    ),
    "first_dayun_is_a_later_one": lambda c: (
        "首步大运" + c.natal["dayun"]["current_candidates"][0]["ganzhi"] + "。",
        [ref(c.session, ":dayun:")],
    ),
    "flow_relation_kind": lambda c: (
        f"流月{c.period['periods'][0]['pillars']['month']}与月柱"
        f"{c.natal['pillars']['month']}相合。",
        [flow_month_ref(c)],
    ),
    # The same wrong date is rejected when no comma separates it from the aspect.
    "transit_date_before_a_comma": lambda c: transit_sentence(c, 4, "，"),
}


def assert_rejected(session, question_type, sentence):
    body, refs = sentence
    assert validate_reading(layered(session, question_type, body, refs), session), body


@pytest.mark.parametrize("mutation", sorted(CHART_MUTATIONS))
async def test_chart_mutation_is_rejected(charts, mutation):
    assert_rejected(charts.session, "timing", CHART_MUTATIONS[mutation](charts))


@pytest.mark.xfail(strict=True, reason="漏拦：留给流水线的闭集比对（P1–P3）")
@pytest.mark.parametrize("mutation", sorted(CHART_MISSED))
async def test_chart_mutation_missed_today(charts, mutation):
    assert_rejected(charts.session, "timing", CHART_MISSED[mutation](charts))


async def test_tarot_mutations_are_rejected(runtime, tarot):
    card = tarot[1]
    undrawn = "恋人" if all(c["name"] != "恋人" for c in tarot) else "隐士"
    for body in (
        f"现在位是{card['name']}{opposite(card)}。",
        f"现在位是【{undrawn}】正位。",
        # Denying the drawn orientation does not make the asserted wrong one acceptable.
        f"这次抽到的是{card['name']}{opposite(card)}，不是{card['name']}{orientation(card)}。",
        f"{card['name']}{opposite(card)}一般表示阻滞，这次抽到的正是它。",
    ):
        assert_rejected(runtime.session, "tarot", (body, [card["ref_id"]]))


async def test_negation_does_not_hide_a_wrong_position(charts):
    s = charts.session
    sun = next(p for p in charts.chart["planets"] if p["body"] == "Sun")
    actual = SIGN_ZH[SIGNS.index(sun["sign"])]
    elsewhere = next(zh for zh in SIGN_ZH if zh != actual)
    sign_ref, house_ref = ref(s, f":Sun:{sun['sign']}"), ref(s, f":Sun:house{sun['house']}")
    assert_rejected(s, "timing", (f"太阳不在{actual}座，而在{elsewhere}座。", [sign_ref]))
    assert_rejected(
        s, "timing", (f"太阳不在第{sun['house']}宫，而在第{wrong_house(sun)}宫。", [house_ref])
    )


@pytest.mark.xfail(strict=True, reason="漏拦：牌位张冠李戴，留给流水线的闭集比对")
async def test_tarot_positions_swapped_missed_today(runtime, tarot):
    first, _, third = tarot
    body = (
        f"{first['label']}位是{third['name']}{orientation(third)}，"
        f"{third['label']}位是{first['name']}{orientation(first)}。"
    )
    assert_rejected(runtime.session, "tarot", (body, [c["ref_id"] for c in tarot]))


@pytest.mark.xfail(strict=True, reason="漏拦：未抽出的大阿卡纳不带牌名标记，留给流水线的闭集比对")
async def test_tarot_undrawn_major_without_marker_missed_today(runtime, tarot):
    undrawn = "恋人" if all(c["name"] != "恋人" for c in tarot) else "隐士"
    body = f"现在位抽到了{undrawn}，象征选择。"
    assert_rejected(runtime.session, "tarot", (body, [tarot[1]["ref_id"]]))


async def test_daily_mutations_are_rejected(runtime, daily):
    s, day, card = runtime.session, daily["day"], daily["card"]
    day_ref = ref(s, f"{day['segments'][0]['start_utc']}:{day['pillar']}:{day['ten_god']}")
    assert_rejected(s, "daily", (f"今天流日{unused_jiazi(s)}。", [day_ref]))
    assert_rejected(
        s, "daily", (f"今天的提示牌是{card['name']}{opposite(card)}。", [card["ref_id"]])
    )


@pytest.mark.xfail(strict=True, reason="漏拦：流日十神写错，留给流水线的闭集比对")
async def test_daily_ten_god_missed_today(runtime, daily):
    s, day = runtime.session, daily["day"]
    day_ref = ref(s, f"{day['segments'][0]['start_utc']}:{day['pillar']}:{day['ten_god']}")
    wrong = next(g for g in TEN_GODS if g != day["ten_god"])
    assert_rejected(s, "daily", (f"今天流日{day['pillar']}，十神为{wrong}。", [day_ref]))


async def test_name_mutations_are_rejected(runtime, name):
    s, grids = runtime.session, name["grids"]
    person = ref(s, f":人格:{grids['人格']}")
    assert_rejected(s, "name", (f"人格{grids['人格'] + 1}。", [person]))
    other = "木木土" if name["sancai"]["key"] != "木木土" else "火火火"
    assert_rejected(s, "name", (f"三才配置为{other}。", [person]))


async def test_dream_mutations_are_rejected(runtime, dream):
    teeth = ref(runtime.session, ":掉牙")
    assert_rejected(runtime.session, "dream", ("梦见蛇象征转变。", [teeth]))
    assert_rejected(runtime.session, "dream", ("掉牙预示家里会有人生病。", [teeth]))
