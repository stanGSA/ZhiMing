"""Expression-layer policy for authored readings and specialist reports.

Facts stay strict: plugin validators still reject invented 干支, 落座, 宫位, 相位, 牌面, dates
and ref_ids. Wording is no longer policed by rejection where code can repair it, because every
rejection teaches the model to write less:

* disclaimers and internal words are removed (the app adds one disclaimer itself);
* HTML line breaks (``<br>``) become real line breaks;
* ``confidence`` and ``systems_used`` are filled in from what this session actually computed;
* a skipped specialist is disclosed in ``confidence.reason``;
* a remark about the body gets a visible "see a doctor if unwell" note.

Rejection on wording is reserved for certainty claims (一定会/必然/注定…) and for discouraging
medical care. Trends may be stated with 倾向/容易/往往. Checks that only judge style or
completeness are recorded as warnings.
"""

from __future__ import annotations

import re

from common.facts import rendered_texts
from harness.models import ValidationMessage
from knowledge.review import lowest, review_status

DISCLAIMER = re.compile(r"仅供参考|仅供娱乐|仅供[^。！？!?\n]{0,10}反思")
INTERNAL = re.compile(
    r"active_reading_id|missing_dependency|submit_reading|submit_report|"
    r"存储错误|保存失败|未能保存|未经?人工审核"
)
KB_WORD = re.compile(r"知识库(?:的|中的|里的)?(?:释义|条目|解释)?")
# Replies are plain text; a model writing HTML line breaks would show them literally.
BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
SENTENCE = re.compile(r"[^。！？!?\n]*(?:[。！？!?]+|\n|$)")

CERTAINTY = re.compile(r"一定会|一定能|一定是|必然|必定|注定|肯定会|绝对会|百分之百|毫无疑问|铁定")
HARD = re.compile(r"稳赚|必涨|必死|必然确诊")
# Only the approved 稳赚 denial is relaxed; the other hard words retain their policy.
# The object may carry a modifier or quotes (r7: 别把一时的配合顺畅当成稳赚, 别把顺手当稳赚,
# 别把“配合顺”误解为“稳赚”). It is one short phrase without a negation, a contrast, a
# certainty or another hard word, so it cannot hide a second clause or a double negative.
# Frame verbs are checked inside the captured object, not across its boundary: the 应 in
# 市场反应 followed by 当成 is part of a noun, not the modal 应当.
GAIN_OBJECT = (
    r"(?P<object>[“‘「\"']?(?:(?![不没非无别但而却是必]"
    r"|一定|肯定|注定|铁定|绝对|百分|毫无|稳赚)[\u4e00-\u9fff]){1,10}[”’」\"']?)"
)
OBJECT_PREDICATE = re.compile(
    r"当作|当成|视为|看成|看作|想成|认为|认定|应该|应当|理解|解读|作为|误解|误认|错当"
    r"|想(?:复杂|简单)"
)
# One controlled adverbial may stand between the negation and 把, and one adverb before the
# verb (r8: 别在情绪顺畅时把配合或行情当成稳赚, 别因为情绪顺畅就把…当作稳赚, 别把“有机会”
# 直接当成“稳赚”). Its words hold no negation, contrast, 把/将 or certainty either.
PLAIN = r"(?:(?![不没非无别但而却是必把将]|一定|肯定|注定|铁定|绝对|稳赚)[\u4e00-\u9fff])"
DISMISS_ADVERBIAL = (
    rf"(?:(?:在|趁){PLAIN}{{1,8}}(?:时|的时候)|因为{PLAIN}{{1,8}}|一下子|轻易|急着|随便|再)?就?"
)
DISMISS_VERB_ADVERB = r"(?:直接|轻易|简单地?|随便|马上|就)?"
GAIN_DISMISSAL = re.compile(
    # bazi pilot r16, investment #3: “创意与专长可以开源但不宜当作稳赚”.
    r"(?:别|不要|不能|不宜|不应(?:该|当)?|不|并不)"
    rf"(?:{DISMISS_ADVERBIAL}(?:把|将){GAIN_OBJECT}{DISMISS_VERB_ADVERB})?"
    r"(?:当作|当成|当|视为|看成|看作|理解为|理解成|误解为|误认为|错当成)[“‘「\"']?$"
)
# What may follow a dismissed 稳赚 in its clause: 别当稳赚以外的选择 affirms it.
GAIN_DISMISSED_REST = re.compile(
    # The noun may follow without 的 (r10: 不把“配合感”当稳赚信号).
    r"[”’」\"']?(?:的?(?:事|事情|机会|买卖|生意|保证|承诺|信号|理由|依据|把握))?"
    r"(?:了|啊|呀|哦)?[”’」\"']?\s*(?:[，,。；;！!？?\n—…]|$)"
)
GAIN_DENIAL_NEGATED = re.compile(r"(?:不|非|不是|没有|不得|不能|不可|不可以)(?:说|认为|觉得)?$")
# Shared with source checks. Only enumerated subjects and predicates are accepted;
# an intervening predicate or contrast must not hide a separate affirmative claim.
DISCLAIMER_CLAIM = (
    r"(?:现实运势或事件|现实事件|现实发展|现实生活|实际情况|使用此数的人|个人|精力|事件|困扰|状态|负担)?"
    r"(?:必然|一定会?|注定)(?:会)?"
    r"(?:发生|出现|如此|成立|消退|好转|减轻|顺利|不利|受牵扯|遭遇波折|具备|具有)"
)
NEGATED_DISCLAIMER = re.compile(
    r"(?:并不|并非|不)(?:代表|表示|意味着?|等于|预示|说明)"
    + DISCLAIMER_CLAIM
    + rf"(?:(?:或|以及){DISCLAIMER_CLAIM})*"
)
# A negation cancels a certainty word only when it governs that word: directly ("不一定会",
# "并非注定", "不是必然") or through a negated framing verb earlier in the clause ("不代表事件
# 必然发生", "并不意味着一定会"). A stray negative character ("不久后你一定会…") does not.
DIRECT_NEGATION = re.compile(
    r"(?:不|并不|并非|非|未|绝非|不是|并不是|不会|不能|无法)(?:是|会|就|能)?$"
)
NEGATED_FRAME = re.compile(
    r"(?:不|并不|并非|未|没有|不能|无法|不会|并不会|没人能|没有人能|谁也不能)"
    r"(?:代表|意味着?|等于|说明|表示|保证|确定|断定|断言|预示|预言|预告|告诉|说|认为|觉得)"
    r"|(?:别|不要)(?:以为|认为|觉得)"
)
# "不是说/并非指" report a clause, and "并非/绝非" negate one ("并非股价一定会涨"): both govern
# its subject, as a framing verb does. A bare "不是" names what something is ("这不是坏事"), so
# a clause after it is a new one unless it starts with a pronoun or a demonstrative ("不是你一定
# 会失败", "不是这只股票一定会涨").
NEGATED_SUBJECT = re.compile(r"(?:并非|绝非|并不是|不是)(?:说|指)|并非|绝非")
COPULA = re.compile(r"(?:并不是|不是)")
# What a negation governs is the claim's own subject. Regular expressions cannot parse it, so
# the phrase is held to the shape of one short noun phrase, such as "行情", "某件事", "具体事件",
# "留下就", "你们的关系" or "你今天": anything that might be a second clause is refused. A
# negation, a contrast, a claim of its own, or a second subject (a pronoun, a demonstrative, a
# noun after a predicate) ends what it governs: "不认为这很难你一定会成功" negates "很难",
# "这不是坏事这只股票一定会涨" negates "坏事", neither the claim.
SUBJECT_TEXT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9“”‘’「」]*")
MODIFIERS = re.compile(r"(?:就|也|都|会|能|将|真的|最终|近期|这个月|下个月|以后|未来|现实中)+$")
SUBJECT_BREAK = re.compile(
    r"[不没非无]|未(?!来)|但|而|或|却|可是|然而|就算|即使|" + CERTAINTY.pattern
)
PRONOUNS = r"你们|我们|他们|她们|咱们|你|您|我|他|她|它"
DEMONSTRATIVE = r"(?:这|那|该|某)(?:只|个|次|段|份|笔|些|种|件|张|位|家|条)?"
# A noun phrase: an optional pronoun, demonstrative and "…的", then its head. A head of four
# characters could be two words, a predicate and a new subject ("亏损行情", "过去的亏损股价"),
# whatever is in front of it, so it needs a modifier of its own ("具体事件", "全部投入");
# otherwise three at most.
LEAD = re.compile(
    rf"(?:(?:{PRONOUNS})(?:的|俩)?)?(?:{DEMONSTRATIVE}的?)?(?:[\u4e00-\u9fffA-Za-z0-9]{{1,4}}的)?"
)
HEAD = re.compile(r"[\u4e00-\u9fffA-Za-z0-9“”‘’「」]{0,4}")
HEAD_MODIFIER = re.compile(r"具体|全部|所有|整体|实际|现实|近期|未来")
# "行情对你必然有利": a pronoun after 对/给/让… is an object, not a new subject.
TRAILING_OBJECT = re.compile(rf"(?:对|给|让|和|跟|与|向|替|为)(?:{PRONOUNS})$")
LEADING = re.compile(rf"^(?:(?:{PRONOUNS})(?:的|俩)?)?(?:{DEMONSTRATIVE}的?)?")
LATER_SUBJECT = re.compile(rf"(?:{PRONOUNS})|(?:这|那)(?=[\u4e00-\u9fff])")
SUBJECT_START = re.compile(rf"(?:{PRONOUNS}|{DEMONSTRATIVE})")
# The certainty word as a noun under a negation: "这不是一种必然", "没有什么是注定的",
# "不必把这理解为必然".
NEGATED_NOUN = re.compile(
    r"(?:不是|并不是|并非|绝非)(?:一种|一个)$"
    r"|(?:没有|并没有)(?:什么|哪种|哪个|任何)(?:结果|事情|事|结局)?(?:是|会是)$"
    # A controlled object cannot swallow another predicate or instruction before the frame.
    r"|(?:不必|不要|别|不用|不是|并不是|并非)把"
    r"(?:它们?|这(?:些|张牌)?|那(?:些|张牌)?|牌面|"
    r"[这那](?:个|种|些|件)?(?:数理|结果|意象|梦境|梦|牌面|牌|事件|趋势))?"
    r"(?:理解为|理解成|看作|看成|当作|当成|视为|想成|解读为|解读成)$"
    # The same frame with any short plain object, as for 稳赚 (r8 daily_lucky_color#3:
    # 别把配合当成必然有利). Double negatives (不得不把, 不是不把) are not denials.
    r"|(?<!不)(?<!非)(?<!不是)(?<!没有)(?<!不得)(?<!不能)(?<!不可)"
    rf"(?:不必|不要|别|不用|不能|不应(?:该|当)?)(?:{DISMISS_ADVERBIAL})(?:把|将){GAIN_OBJECT}"
    rf"{DISMISS_VERB_ADVERB}(?:理解为|理解成|看作|看成|当作|当成|当|视为|想成|解读为|解读成)$"
)
# “不是事情必然顺利的保证” (r8 daily_today_general#2) denies a guarantee: the copula governs the
# claim through the noun that ends its phrase. The subject between is one short plain phrase,
# the rest of the phrase holds no break, and a question (…的保证吗) asks the opposite.
NEGATED_HEAD_BEFORE = re.compile(
    rf"(?:不是|并不是|并非|绝非|不等于|不构成|不能作为|不作为){PLAIN}{{0,6}}$"
)
NEGATED_HEAD_AFTER = re.compile(
    rf"{PLAIN}{{0,8}}?的(?:保证|结论|定论|预言|承诺|依据|证明|意思)(?![^。；;！!？?\n]*[吗么？?])"
)
CLAUSE_START = re.compile(r".*[，,。；;：:！!？?\n]")
# Negating the opposite or the alternatives does not negate the certainty itself.
DENIAL_REVERSAL = re.compile(r"反面|对立面|反义|相反|以外|之外")

HEALTH = re.compile(
    r"健康|身体|体力|透支|睡眠|失眠|熬夜|免疫|疲劳|脏腑|[心肝脾肺肾]脏|肾|肝|脾胃|肠胃|"
    r"泌尿|血压|头痛|头疼|疾病|生病|病症|症状|养生|养肾|养肝"
)
# Seeking care, as an action; "医院附近" or "医生朋友" are not advice.
CARE_ACTION = re.compile(
    r"就医|就诊|看医生|找医生|咨询医生|请医生|去医院|到医院|医院检查|做检查|体检|"
    r"专业医疗|医疗帮助|医疗机构"
)
DISCOURAGE = re.compile(
    r"(?:无需|无须|不用|不必|没必要|不需要|用不着|不建议|不推荐|不应当?|不应该|"
    r"不能|不可|不得|别|不要|免得|省得|避免)"
    r"(?:再|去|特意|专门|马上|立即|及时|尽快|主动|直接|考虑|寻求|接受|进行)*$"
)
ADVISE = re.compile(r"请|应当|应该|应|建议|及时|尽快|务必|最好|宜|需要|如有|若有|如果|一旦|记得")
# Medical negation deliberately excludes "不代表/不说明": these can govern a
# separate diagnosis, as in "这不代表你有病不需要就医".
CARE_NEGATED_BELIEF = re.compile(
    r"(?:不要|别|不能|不可|不应|不应该|并不|不)(?:以为|认为|觉得)"
    r"(?:你们|我们|你|您|我)?"
    r"(?:(?:身体不适|有症状|生病|有病)(?:时|的时候))?$"
)
CARE_DIRECT_NEGATION = re.compile(r"(?:并非|绝非|并不是|不是)$")
CARE_CONDITION = re.compile(r"(?:如果|若|万一|一旦)(?:你们|我们|你|您|我)?(?:暂时|一时)?$")
# A repeated character is ambiguous across word boundaries (副作用不用, 只要不要).
# Exempt a question only at the clause's start, after its subject, or in a question frame.
# A clause may open with a connective (r7 dream_hospital_health#3: 那要不要去做检查).
CARE_QUESTION_SUBJECT = re.compile(
    r"(?:那么|那|所以)?(?:你们|我们|您|你|我|自己)?(?:现在|到底|究竟)?"
)
CARE_QUESTION_FRAME = re.compile(
    r"(?:关于|至于|问(?:一下)?|想知道|想了解|确认|考虑|判断|决定)"
    r"(?:你们|我们|您|你|我|自己)?(?:现在|到底|究竟)?$"
)
A_NOT_A_FORMS = {
    "不要": ("要",),
    "不需要": ("需要", "需"),
    "不用": ("用",),
    "不能": ("能",),
    "不应该": ("应该", "应"),
    "不应当": ("应当", "应"),
    "不应": ("应",),
}
HEALTH_NOTE = "如有身体不适，请及时就医，以医生的诊断为准。"
# Medication instructions are hard failures in every mode, including with a semantic judge.
STOP_MEDICATION = re.compile(
    r"停药|停用(?:药物|药品)|停止(?:服药|用药|治疗)|不(?:用|必|需要)(?:再)?(?:吃药|服药|用药)"
)
MEDICATION_DIRECTIVE = re.compile(
    r"(?:必须|务必|应该|应当|建议|可以|需要|最好|不妨|请|尽快|立即|马上|直接|自行|擅自)"
    r"(?:你|您|先|就|再|马上|立即|直接|自行|擅自|突然|逐渐|逐步)*[“‘「\"]?$"
)
MEDICATION_NEGATION = re.compile(
    r"(?:不(?:能|可(?:以)?|应(?:该|当)?|建议|必|需要)|不要|别|勿|切勿|禁止|避免|无需|无须|不得)"
    r"(?:再|自行|擅自|随意|随便|轻易|马上|立即|直接|突然|贸然|建议|说|认为|以为|觉得|断言|"
    r"表示|告诉|让|要求|你|您|就|必须|可以|务必)*[“‘「\"]?$"
)
MEDICATION_AUTHORITY = re.compile(
    r"(?:遵循?|按照?|根据)(?:医嘱|医生(?:的)?(?:指导|建议))|"
    r"(?:由|请|让)(?:医生|医师).{0,12}(?:决定|评估|判断)|"
    r"(?:医生|医师)(?:指导|确认|同意|评估)(?:后|下)"
)
MEDICATION_REFUTED = re.compile(
    r"^[”’」\"](?:的)?(?:这(?:种|类))?(?:说法|建议|结论)?(?:是)?"
    r"(?:不(?:正确|可靠|成立|可信)|错误|没有依据|无依据|不可采纳)"
)
# Lowest review level of the meanings used → confidence cap and the fact the reason must state.
# Model cross-review is never written as human review (项目完善计划书 4.2; cap: stage 1 decision 2).
REVIEW_CAP = {"draft": "low", "model_reviewed": "medium", "human_reviewed": None}
REVIEW_NOTE = {"draft": "释义未经审核", "model_reviewed": "释义经模型交叉审核，未经人工审核"}
# Wordings that already state the level; any other clause about 审核 is replaced by the note.
REVIEW_STATED = {
    "draft": re.compile(r"未经?(?:人工)?审核|没有(?:经过)?(?:人工)?审核"),
    "model_reviewed": re.compile(r"模型交叉审核.*未经?人工审核|未经?人工审核.*模型交叉审核"),
}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
REASON_CLAUSE = re.compile(r"[^，,。；;\n]*(?:[，,。；;\n]+|$)")


def warn(state: dict, message: str) -> None:
    """Record a style or completeness finding without rejecting the answer."""
    warnings = state.setdefault("output_warnings", [])
    if message not in warnings:
        warnings.append(message)


def normalize_breaks(text: str) -> str:
    """Normalize plain-text line breaks without removing metadata or changing identifiers."""
    return BREAK_TAG.sub("\n", text)


def clean(text: str) -> str:
    """Drop sentences carrying a disclaimer or internal state; keep the rest verbatim."""
    if not text:
        return text
    text = normalize_breaks(text)
    kept = [
        piece
        for piece in SENTENCE.findall(text)
        if piece and not DISCLAIMER.search(piece) and not INTERNAL.search(piece)
    ]
    result = KB_WORD.sub("传统释义", "".join(kept)).strip()
    # A field that is nothing but a disclaimer stays as written; the hard check rejects it.
    return result or text


def clean_list(values: list[str]) -> list[str]:
    """List items that are nothing but a disclaimer or internal note are dropped."""
    cleaned = [clean(value) for value in values]
    return [v for v in cleaned if not (DISCLAIMER.search(v) or INTERNAL.search(v))]


def authored_texts(reading) -> list[str]:
    """Every authored string of a reading, for policy checks (confidence.reason excluded)."""
    return [
        reading.summary,
        *[part for s in reading.sections for part in (s.title, s.body)],
        *[e.reading for e in reading.evidence],
        *reading.advice,
        reading.closing,
        *reading.resonances,
        *[part for t in reading.tensions for part in (t.theme, *t.sides, t.how_to_read)],
        *[part for t in reading.timeline for part in (t.period, t.note)],
        *reading.followups,
        reading.safety.note,
    ]


def clause_before(text: str, start: int, width: int = 16) -> str:
    """The part of the clause in front of a match, at most ``width`` characters."""
    return CLAUSE_START.sub("", text[max(0, start - width) : start])


OPEN_QUOTE = re.compile(r"[“‘「『\"']+\s*$")
QUOTE_PAIRS = {"“": "”", "‘": "’", "「": "」", "『": "』", '"': '"', "'": "'"}
CERTAINTY_DOUBTED = re.compile(
    r"(?:警惕|提防|当心|小心|怀疑|质疑|远离|拒绝|摒弃|抛开|放下|"
    r"别信|不要信|别轻信|不要轻信|不轻信|千万别信|不信)"
    r"(?:任何|所有|这类|各种|一切|那些|那种|所谓|什么)*$"
)
CERTAINTY_CLAIM_NOUN = re.compile(
    r"(?:[、，,和与及或]?\s*[“‘「『\"'][^”’」』\"'。！？!?；;\n]{1,24}[”’」』\"'])*"
    r"(?:之类|一类|这类|这种|那套|那种|这样)?的?"
    r"(?:说法|话术|说辞|话|论调|断言|定论|预言|承诺|保证|宿命论|命定论|观念|想法|讲法|判断|结论)"
)
CHAINED_QUOTES_BEFORE = re.compile(
    r"(?:[“‘「『\"'][^”’」』\"'。！？!?；;\n]{1,24}[”’」』\"']\s*[、和与及或]?\s*)+$"
)
REFUTED_QUOTE_LEAD = re.compile(
    r"(?:"
    r"(?:凡是|任何|一切|所有|无论谁|不管谁)?(?:有人|别人|外人|外界)?"
    r"(?:跟你说|对你说|说|讲|声称|宣称|鼓吹|断言|号称)?(?:什么|所谓|那种|这类|这种|那些)?"
    r"|(?:这(?:种|类|套|句)|那(?:种|类|套|句)|所谓)"
    r"|(?:把(?:命盘|八字|星盘|塔罗|牌面|卦象|数理|梦境|运势|它))?"
    r"(?:当成|当作|视为|看成|看作|理解成|理解为)(?:什么|所谓|一种)?"
    r")"
)
SPEECH_QUOTE_LEAD = re.compile(
    r"(?:凡是|任何|有人|别人)(?:跟你说|对你说|说|讲|声称|宣称|鼓吹|断言)$"
)
REFUTATION_BRIDGE = re.compile(
    r"(?:\s*[，,]\s*)?"
    r"(?:其实|本身|本来|从来|向来|压根|往往|通通|统统|全|都|一律|一概|根本|完全|纯属|只是|皆|多半|自然|显然|就|也|更)*"
)
CERTAINTY_REFUTATION = re.compile(
    r"(?:"
    r"(?:是|属于|纯属|皆属|都属|皆是|都是|皆为|算|算是)"
    r"(?:越界|迷信|噱头|误导|伪命题|无稽之谈|空话|瞎话|骗人的?|错误的?|错的|假的|"
    r"站不住脚的?|靠不住的?|不可信的?|不成立的?|不靠谱的?|没有依据的?)"
    r"|(?:越界|迷信|站不住脚|靠不住|当不得真|算不得数|不值一信)"
    r"|(?:并)?不(?:成立|可信|靠谱|准确|客观|真实|存在|能信|能当真|值得信|可采纳|可取|合理|科学|负责任)"
    r"|(?:毫无|没有(?:任何|事实|命理|现实)?|无|缺乏)(?:依据|根据|道理|意义|支撑)"
    r")"
)
REFUTATION_TAIL_UNDONE = re.compile(r"不对|不真|不实|错的|假的|不成立|站不住脚")


def sentence_around(text: str, start: int, end: int, limit: int = 90) -> str:
    """Extract the single sentence around ``start:end`` for actionable validator errors."""
    sentence = text
    offset = start
    for match in re.finditer(r"[^。！？!?\n]+(?:[。！？!?]+|$)", text):
        if match.start() <= start < match.end() or (start == len(text) and match.end() == start):
            sentence = match.group()
            offset = start - match.start()
            break
    compact = re.sub(r"\s+", " ", sentence).strip()
    if len(compact) <= limit:
        return compact
    half = max(16, (limit - (end - start)) // 2)
    left = max(0, min(offset, len(compact) - 1) - half)
    right = min(len(compact), left + limit)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(compact) else ""
    return f"{prefix}{compact[left:right].strip()}{suffix}"


def _enclosing_quote(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Return ``(open_idx, close_idx)`` when ``start:end`` sits inside one short closed quote."""
    open_idx = -1
    close_ch = ""
    for i in range(start - 1, max(-1, start - 37), -1):
        ch = text[i]
        if ch in "。！？!?；;\n”’」』":
            return None
        if ch in QUOTE_PAIRS:
            if ch in ('"', "'"):
                prior = re.split(r"[。！？!?；;\n]", text[:i])[-1]
                if prior.count(ch) % 2 == 1:
                    return None
            open_idx = i
            close_ch = QUOTE_PAIRS[ch]
            break
    if open_idx < 0:
        return None
    for j in range(end, min(len(text), end + 37)):
        ch = text[j]
        if ch == close_ch:
            if j - open_idx - 1 > 36:
                return None
            return open_idx, j
        if ch in "。！？!?；;\n“‘「『":
            return None
    return None


def quoted_certainty_refuted(text: str, start: int, end: int) -> bool:
    """Whether ``start:end`` is inside a quoted fatalistic claim that the sentence doubts/refutes."""
    span = _enclosing_quote(text, start, end)
    if span is None:
        return False
    open_idx, close_idx = span
    raw_before = CHAINED_QUOTES_BEFORE.sub("", text[max(0, open_idx - 48) : open_idx])
    before_quote = CLAUSE_START.sub("", raw_before)
    lead = re.split(r"但是|然而|不过|反而|而是|可是|却|但", before_quote)[-1].strip()
    after_quote = text[close_idx + 1 :]
    noun = CERTAINTY_CLAIM_NOUN.match(after_quote)

    doubted = CERTAINTY_DOUBTED.search(lead)
    if doubted and noun:
        ahead = lead[: doubted.start()]
        if GAIN_DOUBT_UNDONE.search(ahead) or denial_negated(ahead):
            return False
        return bool(re.match(r"\s*(?:[，,。；;！!\n—…]|$)", after_quote[noun.end() :]))

    addressed = GAIN_ADDRESSED.search(lead)
    if addressed and noun:
        ahead = lead[: addressed.start()]
        if GAIN_DOUBT_UNDONE.search(ahead) or denial_negated(ahead):
            return False
        demand = GAIN_DEMANDED.match(after_quote, noun.end())
        if not demand or GAIN_DEMAND_REVERSED.match(after_quote, demand.end()):
            return False
        clause_end = re.match(
            r"([^，,。；;：:！!？?\n]*)([，,。；;：:！!？?\n]?)", after_quote[demand.end() :]
        )
        tail, punct = clause_end[1], clause_end[2]
        return punct not in ("？", "?") and not re.search(r"[吗么]\s*$", tail)

    if not REFUTED_QUOTE_LEAD.fullmatch(lead):
        return False
    if noun is not None:
        after_subject = after_quote[noun.end() :]
    elif SPEECH_QUOTE_LEAD.search(lead):
        after_subject = after_quote
    else:
        return False
    bridge = REFUTATION_BRIDGE.match(after_subject)
    refuted = CERTAINTY_REFUTATION.match(after_subject, bridge.end())
    if not refuted:
        return False
    clause_end = re.match(
        r"([^，,。；;：:！!？?\n]*)([，,。；;：:！!？?\n]?)", after_subject[refuted.end() :]
    )
    tail, punct = clause_end[1], clause_end[2]
    if (
        punct in ("？", "?")
        or re.search(r"[吗么]\s*$", tail)
        or DENIAL_REVERSAL.search(tail)
        or GAIN_DEMAND_REVERSED.match(tail)
        or REFUTATION_TAIL_UNDONE.search(tail)
    ):
        return False
    return True


def certainty_violation(texts) -> tuple[str, str] | None:
    """``(word, offending_sentence)`` for the first ungoverned certainty claim, else None."""
    for raw in texts:
        if not raw:
            continue
        text = NEGATED_DISCLAIMER.sub(lambda m: " " * len(m[0]), raw)
        for match in CERTAINTY.finditer(text):
            if quoted_certainty_refuted(text, match.start(), match.end()):
                continue
            # An opening quotation mark between a negation and the word (不是“必然发财”, bazi
            # pilot r1) is punctuation, not a new clause: the words are read as without it.
            before = OPEN_QUOTE.sub("", clause_before(text, match.start(), 40))
            denied = negates_claim(before)
            if denied and not governing_denial(NEGATED_NOUN, before):
                continue
            if (denied or negated_head(text, match, before)) and not denial_reversed(
                text[match.end() :]
            ):
                continue
            return match.group(), sentence_around(raw, match.start(), match.end())
    return None


def certainty_claim(texts) -> str | None:
    """The first certainty word that no negation in its clause governs."""
    found = certainty_violation(texts)
    return found[0] if found else None


def negated_head(text: str, match: re.Match, before: str) -> bool:
    """“不是X必然Y的保证”: a copula denies the claim through the noun closing its phrase."""
    before = re.split(r"但是|然而|不过|反而|而是|可是|却|但", before)[-1]
    return bool(
        governing_denial(NEGATED_HEAD_BEFORE, before)
        and NEGATED_HEAD_AFTER.match(text, match.end())
    )


def denial_reversed(rest: str) -> bool:
    """Check only this complement: a later clause's 相反 does not undo its denial."""
    clause = re.split(r"[，,。；;：:！!？?\n]", rest, maxsplit=1)[0]
    return bool(DENIAL_REVERSAL.search(clause))


def denial_negated(prefix: str) -> bool:
    """An outer denial may govern an intervening subject: 不能说这不是… ."""
    return bool(
        GAIN_DENIAL_NEGATED.search(prefix)
        or any(
            claim_subject(prefix[match.end() :])
            for pattern in (NEGATED_FRAME, NEGATED_SUBJECT)
            for match in pattern.finditer(prefix)
        )
    )


def governing_denial(pattern: re.Pattern, before: str) -> re.Match | None:
    match = pattern.search(before)
    if match is None or denial_negated(before[: match.start()]):
        return None
    # Reject a second predicate in the object while allowing ordinary compound nouns such
    # as 反应, 想象, 看好 and 认可. Inspect only the object, never the following frame verb.
    if OBJECT_PREDICATE.search(match.groupdict().get("object") or ""):
        return None
    return match


# “对任何“稳赚”说法都要求看到成本和最坏情况” (bazi pilot r9, investment #2): a quoted 稳赚 named
# as someone's claim (说法, 承诺…) that the sentence doubts is a mention, not a promise (owner,
# 2026-11-11: only quoted mentions). The doubt is a frame before the quote (警惕, 别信) or a
# demand after the noun (对……都要核实); a negated frame (不用警惕, 不必核实) is no doubt.
QUOTED_GAIN = re.compile(r"[“‘「\"']$")
# bazi pilot r16, investment #3: “对‘稳赚’‘错过就没有’的话术保持距离”“面对‘稳赚不赔’‘错过就没有’
# 这类说辞，先问清依据和退出条件”: a quote may run on past 稳赚 (稳赚不赔) and others may follow it
# before the noun.
GAIN_CLAIM_NOUN = re.compile(
    r"[^”’」\"'，,。；;！？!?\n]{0,4}[”’」\"']"
    r"(?:[、，,和与及或]?[“‘「\"'][^”’」\"'，,。；;！？!?\n]{1,12}[”’」\"'])*"
    r"(?:之类|一类|这类|这种)?的?(?:说法|话术|说辞|话|承诺|宣传|消息|推荐|论调|口号|许诺|言论)"
)
GAIN_DOUBTED = re.compile(
    r"(?:警惕|提防|当心|小心|怀疑|质疑|远离|别信|不要信|别轻信|不要轻信|不轻信|千万别信)"
    r"(?:任何|所有|这类|各种|一切|那些)?(?:所谓)?$"
)
# bazi pilot r11, investment #1: “如果你正被某个“稳赚”说法打动，先回到预算和规则上……而不是凭一时
# 情绪加码”: someone's claim in a condition, answered with restraint in the same sentence.
GAIN_TEMPTED = re.compile(
    r"(?:如果|若|要是|万一|假如|一旦)(?:你|您)?(?:正在|正)?(?:被|受)(?:某个|某种|这类|任何|一些|所谓)*$"
)
GAIN_MOVED = re.compile(r"打动|吸引|诱惑|说动|带动|鼓动|触动")
# Read the consequent's first predicate, not a stray 先 or a denied 核实 later on.
GAIN_RESTRAINED = re.compile(
    r"\s*[，,：:]?\s*(?:就|则|那么|也|请)?(?:先|要先)?"
    r"(?:回到(?:预算|规则)(?:和规则)?上?|冷静(?:下来|一下)?|"
    r"暂停(?:决定|操作|投入)?|放一放|把(?:这个)?(?:念头|想法|决定)放一放|"
    r"核实(?:风险|成本|预算|信息|说法|资金安排)?(?:清楚)?|"
    r"(?:别|不要|不必)(?:急着|急于|马上|立即)?"
    r"(?:动用(?:全部)?积蓄|投入|加码|加仓|行动|做决定))"
    r"(?=\s*(?:[，,。；;！？!?\n]|$))"
)
GAIN_DOUBT_UNDONE = re.compile(r"(?:不用|不必|无需|无须|别|不要|没必要|用不着|不需要)$")
# bazi pilot r22, investment #2: “遇到“稳赚”说法多问几个为什么” meets the claim and doubts it.
GAIN_ADDRESSED = re.compile(
    r"(?:对(?:待)?|遇到|碰到|遇上|听到|面对)(?:任何|所有|这类|各种|一切|那些)?(?:所谓)?$"
)
GAIN_DEMANDED = re.compile(
    r"(?:[，,]\s*)?(?:都|也|一律|一概)?(?:先|要|要求|需要|得|应|应该|必须)*(?:先)?"
    r"(?:看到|看清|核实|查清|核对|追问|问清|警惕|存疑|打个?问号|保持(?:警惕|怀疑|距离)|多问(?:几个|一句|一下|几句)?(?:为什么|依据)?|多核实)"
)
# A predicate can be rejected after it is named: “保持距离是不必要的” does not
# recommend caution. Check its own complement, not a negative in a later clause.
GAIN_DEMAND_REVERSED = re.compile(
    r"[ \t]*(?:的?(?:做法|要求|行为|建议))?(?:其实|根本|完全|也|都|并|只是|是)*"
    r"(?:不(?:必|必要|需要|应该|应当|值得)|(?:不是|非)(?:必要|需要|值得|必须)|"
    r"没(?:有)?(?:必要|意义|用)|无(?:需|须|意义)|多此一举)"
)


def quoted_gain_mention(text: str, start: int, end: int) -> bool:
    """Whether the 稳赚 at start:end is quoted as a claim the sentence doubts."""
    before = clause_before(text, start, 40)
    if not QUOTED_GAIN.search(before):
        return False
    noun = GAIN_CLAIM_NOUN.match(text, end)
    if not noun:
        return False
    lead = QUOTED_GAIN.sub("", before)
    doubted = GAIN_DOUBTED.search(lead)
    if doubted:
        ahead = lead[: doubted.start()]
        return not (GAIN_DOUBT_UNDONE.search(ahead) or denial_negated(ahead))
    tempted = GAIN_TEMPTED.search(lead)
    if tempted and not denial_negated(lead[: tempted.start()]):
        rest = re.split(r"[。！？!?\n]", text[noun.end() :])[0]
        moved = GAIN_MOVED.match(rest)
        return bool(moved and GAIN_RESTRAINED.match(rest[moved.end() :]))
    addressed = GAIN_ADDRESSED.search(lead)
    if addressed:
        ahead = lead[: addressed.start()]
        if GAIN_DOUBT_UNDONE.search(ahead) or denial_negated(ahead):
            return False
        demand = GAIN_DEMANDED.match(text, noun.end())
        return bool(demand and not GAIN_DEMAND_REVERSED.match(text, demand.end()))
    return False


def hard_claim_violation(texts) -> tuple[str, str] | None:
    """``(word, offending_sentence)`` for the first ungoverned hard claim, else None."""
    for text in texts:
        for match in HARD.finditer(text or ""):
            if match[0] == "稳赚":
                if quoted_gain_mention(text, match.start(), match.end()):
                    continue
                before = clause_before(text, match.start(), 40)
                before = re.split(r"但是|然而|不过|反而|而是|可是|却|但", before)[-1]
                denial = GAIN_DISMISSAL.search(before) or DIRECT_NEGATION.search(before)
                if denial and denial_negated(before[: denial.start()]):
                    return match[0], sentence_around(text, match.start(), match.end())
                rest = text[match.end() :]
                if (governing_denial(GAIN_DISMISSAL, before) or negates_claim(before)) and (
                    GAIN_DISMISSED_REST.match(rest)
                ):
                    continue
            return match[0], sentence_around(text, match.start(), match.end())
    return None


def hard_claim(texts) -> str | None:
    """Hard words, except a governing denial of 稳赚 (owner decision for P2 r7).

    Each occurrence and field has its own scope: 别把配合当稳赚 does not authorise
    a later 这笔投资稳赚. Double negatives must not be read as disclaimers either.
    """
    found = hard_claim_violation(texts)
    return found[0] if found else None


def negates_claim(before: str) -> bool:
    """Only a governing negation cancels a claim, never an unrelated negative character.

    A subject may intervene in “并非你一定会…”. A contrast starts a new assertion even
    without a comma (“不代表过去不好但你一定会…”).
    """
    before = re.split(r"但是|然而|不过|反而|而是|但", before)[-1].strip()
    return bool(
        governing_denial(DIRECT_NEGATION, before)
        or governing_denial(NEGATED_NOUN, before)
        or any(
            not denial_negated(before[: match.start()]) and claim_subject(before[match.end() :])
            for pattern in (NEGATED_FRAME, NEGATED_SUBJECT)
            for match in pattern.finditer(before)
        )
        or any(
            not denial_negated(before[: match.start()])
            and claim_subject(rest)
            and (not rest or SUBJECT_START.match(rest))
            for match in COPULA.finditer(before)
            for rest in [MODIFIERS.sub("", before[match.end() :].strip())]
        )
    )


def claim_subject(phrase: str) -> bool:
    """Whether ``phrase`` is no more than the subject of the claim that follows it."""
    phrase = TRAILING_OBJECT.sub("", MODIFIERS.sub("", phrase.strip()))
    if not SUBJECT_TEXT.fullmatch(phrase) or SUBJECT_BREAK.search(phrase):
        return False
    lead = LEAD.match(phrase).group()
    head = phrase[len(lead) :]
    if not HEAD.fullmatch(head) or (len(head) == 4 and not HEAD_MODIFIER.match(head)):
        return False
    return not LATER_SUBJECT.search(LEADING.sub("", phrase, count=1))


def certainty_error(texts, *, include_quote: bool = False) -> str | None:
    found = certainty_violation(texts)
    if not found:
        return None
    word, snippet = found
    if not include_quote:
        return f"不能使用“{word}”这类确定性说法；趋势可以写“倾向/容易/往往”，请改写后重新提交"
    return ValidationMessage(
        f"不能使用“{word}”这类确定性说法（冲突句子：“{snippet}”）；"
        "请直接改写该句：表达趋势改用“倾向/容易/往往”，反驳宿命论请直接用否定句（如“命理不能决定……”），"
        "切勿仅替换为“必定/一定/必然/肯定会”等同义词后重复提交",
        retry_key="certainty_claim",
    )


def clean_reading(reading) -> None:
    reading.summary = clean(reading.summary)
    for section in reading.sections:
        section.title = clean(section.title)
        section.body = clean(section.body)
    for item in reading.evidence:
        item.reading = clean(item.reading)
    reading.advice = clean_list(reading.advice)
    reading.closing = clean(reading.closing)
    reading.resonances = clean_list(reading.resonances)
    for tension in reading.tensions:
        tension.theme = normalize_breaks(tension.theme)
        tension.how_to_read = clean(tension.how_to_read)
        tension.sides = [clean(side) for side in tension.sides]
    for item in reading.timeline:
        item.period = normalize_breaks(item.period)
        item.note = clean(item.note)
    reading.followups = clean_list(reading.followups)
    reading.safety.note = clean(reading.safety.note)
    reading.confidence.reason = normalize_breaks(reading.confidence.reason)


def mark_unreviewed(confidence, signals) -> None:
    """Cap confidence by the least reviewed meaning used; code sets it instead of rejecting.

    The reason must state that level. A clause about 审核 that states something else (for
    example that a draft was reviewed by a person) is dropped and the note added.
    """
    level = lowest(review_status(s) for s in signals)
    cap = REVIEW_CAP[level]
    if cap is None:
        return
    if CONFIDENCE_RANK[confidence.level] > CONFIDENCE_RANK[cap]:
        confidence.level = cap
    stated = REVIEW_STATED[level]
    clauses = [c for c in REASON_CLAUSE.findall(confidence.reason) if c]
    kept = [c for c in clauses if "审核" not in c or stated.search(c)]
    reason = confidence.reason if kept == clauses else "".join(kept).strip("，, ")
    if not stated.search(reason):
        note = REVIEW_NOTE[level]
        reason = f"{reason.rstrip('。；;，, ')}；{note}。" if reason.strip() else f"{note}。"
    confidence.reason = reason


def a_not_a(before: str, negative: re.Match) -> bool:
    """An A-not-A phrase with an explicit question context, not a cross-word repetition."""
    word = negative.group()
    prefix = before[: negative.start()]
    for denied, positives in A_NOT_A_FORMS.items():
        if not word.startswith(denied):
            continue
        for positive in positives:
            if prefix.endswith(positive):
                context = prefix[: -len(positive)].strip().rstrip("“‘「\"'").rstrip()
                if CARE_QUESTION_SUBJECT.fullmatch(context) or CARE_QUESTION_FRAME.search(context):
                    return True
    return False


def care_advice_detail(texts) -> tuple[bool, str | None, str | None]:
    """(affirmative care advice present, first discouraging phrase, its offending sentence)."""
    advised, discouraged, snippet = False, None, None
    for text in texts:
        for match in CARE_ACTION.finditer(text or ""):
            before = clause_before(text, match.start(), 40)
            negative = DISCOURAGE.search(before)
            if negative and a_not_a(before, negative):
                # “要不要去做检查” asks the question; it neither advises nor discourages.
                continue
            if negative:
                prefix = before[: negative.start()]
                suffix = text[match.end() :]
                # A conditional inability to obtain care is neither a prohibition nor
                # affirmative advice. Other clauses still need checking independently.
                if negative.group().startswith(("不能", "不可")) and (
                    CARE_CONDITION.search(prefix)
                    or re.match(r"(?:时|的时候|的话|的情况下)", suffix)
                ):
                    continue
                # “不要以为不必就医” negates the discouragement; “不建议就医” does not.
                if CARE_DIRECT_NEGATION.search(prefix) or CARE_NEGATED_BELIEF.search(prefix):
                    advised = True
                elif discouraged is None:
                    discouraged = negative.group() + match.group()
                    snippet = sentence_around(text, match.start(), match.end())
            elif ADVISE.search(before):
                advised = True
    return advised, discouraged, snippet


def care_advice(texts) -> tuple[bool, str | None]:
    """(an affirmative "see a doctor" advice is present, the first discouraging phrase)."""
    advised, discouraged, _ = care_advice_detail(texts)
    return advised, discouraged


def medication_error(texts, *, include_quote: bool = False) -> str | None:
    """Reject affirmative medication instructions, keeping negations and clinician referrals."""
    for text in texts:
        for match in STOP_MEDICATION.finditer(text or ""):
            before = clause_before(text, match.start(), 60)
            after = text[match.end() :]
            if (
                MEDICATION_NEGATION.search(before)
                or MEDICATION_REFUTED.match(after)
                or MEDICATION_AUTHORITY.search(before)
            ):
                continue
            if (
                MEDICATION_DIRECTIVE.search(before)
                or match.group().startswith("不")
                or re.match(r"(?:吧|即可|就好|就行)", after)
            ):
                if not include_quote:
                    return "不能给出停药建议；是否调整用药须由医生评估，请改写后重新提交"
                snippet = sentence_around(text, match.start(), match.end())
                return ValidationMessage(
                    f"不能给出停药建议（冲突句子：“{snippet}”）；是否调整用药须由医生评估，请改写后重新提交",
                    retry_key="stop_medication",
                )
    return None


def care_error(texts, *, include_quote: bool = False) -> str | None:
    _, discouraged, snippet = care_advice_detail(texts)
    if discouraged:
        if not include_quote:
            return (
                f"不能劝阻就医（“{discouraged}”）；谈到身体时保留“如有不适请及时就医”的建议，"
                "请改写后重新提交"
            )
        return ValidationMessage(
            f"不能劝阻就医（“{discouraged}”，冲突句子：“{snippet}”）；"
            "谈到身体时保留“如有不适请及时就医”的建议，请改写后重新提交",
            retry_key="discourage_care",
        )
    return None


def add_health_note(reading) -> None:
    """A remark about the body needs a visible, affirmative "see a doctor" advice.

    Only what the user actually sees counts (see rendered_texts); a mention of a hospital or
    a note hidden in an unrendered field does not. Discouraging care is rejected separately.
    """
    if not any(HEALTH.search(t) for t in authored_texts(reading) if t):
        return
    if care_advice(rendered_texts(reading))[0]:
        return
    if care_advice([reading.safety.note])[0]:
        reading.safety.flag = True  # The advice was written but would not have been shown.
        return
    note = reading.safety.note.strip()
    reading.safety.note = f"{note}{'' if not note or note[-1] in '。！!' else '。'}{HEALTH_NOTE}"
    reading.safety.flag = True


def normalize_reading(reading, state: dict) -> None:
    """Repair what code can repair before the hard checks run (idempotent)."""
    state["output_warnings"] = []
    clean_reading(reading)
    signals = state.get("signals") or []
    actual = {s["system"] for s in signals}
    if actual and set(reading.systems_used) != actual:
        ordered = [s for s in dict.fromkeys(reading.systems_used) if s in actual]
        ordered += sorted(actual - set(ordered))
        reading.systems_used = ordered
    mark_unreviewed(reading.confidence, signals)
    if state.get("response_mode") != "followup":
        for system, report in (state.get("specialist_reports") or {}).items():
            if report["status"] == "ok":
                continue
            reason = reading.confidence.reason
            if report["label"] in reason or system in reason:
                continue
            why = report.get("failure") or (
                "需要补充资料" if report["status"] == "needs_input" else "未完成"
            )
            reading.confidence.reason = (
                f"{reason.rstrip('。；; ')}；缺少{report['label']}：{why}。"
                if reason.strip()
                else f"缺少{report['label']}：{why}。"
            )
    add_health_note(reading)


def normalize_report(report, signals) -> None:
    """The specialist counterpart of normalize_reading."""
    report.answer = clean(report.answer)
    report.analysis = clean(report.analysis)
    for point in report.points:
        point.text = clean(point.text)
    report.missing = clean_list(report.missing)
    report.confidence.reason = normalize_breaks(report.confidence.reason)
    mark_unreviewed(report.confidence, signals)
