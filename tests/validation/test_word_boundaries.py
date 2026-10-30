"""Everyday wording that is spelt like a domain term is not a fabricated fact.

Each system checks every reading, so 自己未来 must not read as the pillar 己未, 保持「节制」
as an undrawn card, nor 自信代表 as an interpretation of the dream symbol 信. Each accepted
phrasing is paired with the fabrication it must still reject.
"""

import pytest

from common.schemas import Reading
from knowledge.kb import KnowledgeBase
from plugins.bazi.validation import validate_output as bazi_output
from plugins.dream.match import DreamMatcher
from plugins.dream.validation import validate_output as dream_output
from plugins.tarot.validation import validate_output as tarot_output


def reading(text, systems=("tarot",), question_type="tarot"):
    return Reading(
        question_type=question_type,
        systems_used=list(systems),
        summary="先表态。",
        sections=[dict(title="分析", body=text)],
        evidence=[dict(ref_id="r", reading="")],
        confidence=dict(level="low", reason="象征性解读"),
        safety=dict(flag=False, note=""),
    )


# --- bazi: every reading is scanned for 干支 ---------------------------------------------

TAROT_STATE = dict(facts=["星星"], tarot_result=dict(cards=[dict(name="星星", reversed=False)]))
BAZI_STATE = dict(
    facts=[],
    bazi_result=dict(
        pillars=dict(year="甲子", month="丙寅", day="戊辰", time="壬子"),
        day_master="戊",
        time_known=True,
    ),
)


@pytest.mark.parametrize(
    "text",
    [
        "给自己未来留一点余地。",
        "知己未必在身边，先照顾好自己。",
        "付出的艰辛未必立刻被看见。",
        "先替自己申请一段休整期。",
        "像甲午战争、辛亥革命那样的大变局，不必套到个人身上。",
    ],
)
@pytest.mark.parametrize("state", [TAROT_STATE, BAZI_STATE], ids=["tarot", "bazi"])
def test_ordinary_words_are_not_ganzhi(text, state):
    assert bazi_output(reading(text), dict(state, question="")) is None


@pytest.mark.parametrize(
    "text",
    [
        "今年流年己未，变动较多。",
        "日柱为己未。",
        "大运由己未转入庚申。",
        "就像甲午年那样的转折。",
        "自己的流年己未要多留意。",
    ],
)
def test_written_ganzhi_still_need_a_calculation(text):
    assert "不能编造" in bazi_output(reading(text), dict(BAZI_STATE, question=""))


# --- tarot: quoted major-arcana words need card context ----------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "这段时间保持「节制」，别一次做满。",
        "多一点【力量】感，少一点自我怀疑。",
        "把注意力放回「世界」本身。",
        "【太阳】四分本命月亮，今天节奏偏快。",
        "正义感会帮你守住底线。",
    ],
)
def test_quoted_everyday_words_are_not_undrawn_cards(text):
    assert tarot_output(reading(text), TAROT_STATE) is None


@pytest.mark.parametrize(
    "text",
    [
        "「节制」逆位提醒你放慢。",
        "「节制」提醒你放慢。",
        "这张【力量】说明你有底气。",
        "今天抽到【太阳】，心情明朗。",
        "太阳牌带来好消息。",
        "【高塔】的出现意味着突变。",
        "「高塔」让人不安。",
    ],
)
def test_card_mentions_still_require_the_card_to_be_drawn(text):
    assert "未抽出的牌" in tarot_output(reading(text), TAROT_STATE)


# --- dream: ordinary prose words and denials of prophecy ---------------------------------


@pytest.fixture
def matcher(project):
    kb = KnowledgeBase(project / "data/kb.sqlite")
    yield DreamMatcher(kb.db, kb.version)
    kb.db.close()


DREAM_STATE = dict(calculations={"dream_result:d": dict(hits=[dict(key="蛇")], misses=[])})


def dream_reading(text):
    return reading(text, systems=("dream",), question_type="dream")


@pytest.mark.parametrize(
    "text",
    [
        "梦见蛇往往反映最近的压力；你的自信代表你正在成长。",
        "对手象征现实里的竞争感。",
        "这像一记警钟提示你放慢。",
        "现实中会发生什么并不由梦决定。",
        "梦并不能预示未来。",
    ],
)
def test_everyday_prose_is_not_a_dream_claim(matcher, text):
    assert dream_output(dream_reading(text), DREAM_STATE, matcher) is None


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("信象征远方的消息。", "不是本次命中的意象"),
        ("梦见狗代表忠诚。", "不是本次命中的意象"),
        ("这个梦预示你会发生不好的事。", "预兆"),
        ("梦见蛇预示好运，并不代表坏事。", "预兆"),
    ],
)
def test_dream_claims_outside_the_lookup_still_fail(matcher, text, error):
    assert error in dream_output(dream_reading(text), DREAM_STATE, matcher)


def test_ordinary_words_are_not_dream_symbols(matcher):
    assert [alias for _, _, alias, _ in matcher.spans("你很自信，也找到了帮手和警钟")] == []
    assert matcher.scan("梦见一条蛇和一只狗") == ["蛇", "狗"]
