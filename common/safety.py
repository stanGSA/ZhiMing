"""Application safety routing, before any divination tool can run."""

import re

# Include indirect distress and interpersonal violence from the original eval set.
CRISIS = re.compile(
    r"自杀|不想活|结束生命|伤害自己|活不下去|活着没(?:什么)?(?:意思|意义)|"
    r"撑不下去|如果我不在了|放弃一切|(?:他|她|伴侣|老公).*打我|"
    r"想死|不如死|轻生|割腕|跳楼"
)
AMBIGUOUS_DISTRESS = re.compile(r"消失|解脱|告别|永远睡|再也醒|受不了|熬不|没希望|走了.*轻松")
SAFETY_PROMPT = """只做安全分类，不进行占卜。判断用户是否表达自伤、自杀、严重绝望、受暴力威胁或当前人身危险。
隐晦表达（想永远睡去、消失、告别所有人）也应结合上下文判断；普通的工作辞职、电脑受不了、旅行告别不自动算危机。
只返回JSON对象：{"crisis": true或false}。"""


def support_text(config: dict, region: str | None = None) -> str:
    contacts = config.get("emergency_contacts", {}).get(region or "", [])
    channel = "、".join(contacts) if contacts else "你所在地的急救或报警等紧急服务"
    return (
        "听起来你正在承受很大的痛苦，我很关心你此刻的安全。你现在是否安全，有没有正在伤害自己的想法，或有人正在威胁、伤害你？"
        "如果有立即危险，请联系" + channel + "，或请身边的人帮你联系。"
        "在安全可行的情况下，离开危险环境，把可能伤害自己的物品放远，联系一个信任的人来陪你。"
        "我们先暂停占卜。我可以继续陪你聊，你愿意告诉我现在发生了什么、身边有没有可以联系的人吗？"
    )
