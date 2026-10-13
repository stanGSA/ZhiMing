from plugins.astro.calculator import ASPECTS, BODIES, SIGNS
from plugins.bazi.calculator import GAN, WX, ZHI

TEN_GODS = ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印")
RELATIONS = (
    "天干合",
    "天干冲",
    "地支六合",
    "地支冲",
    "地支害",
    "地支破",
    "地支刑",
    "自刑",
    "三合",
    "三会",
)
NAYIN = (
    "海中金",
    "炉中火",
    "大林木",
    "路旁土",
    "剑锋金",
    "山头火",
    "涧下水",
    "城头土",
    "白蜡金",
    "杨柳木",
    "泉中水",
    "屋上土",
    "霹雳火",
    "松柏木",
    "长流水",
    "沙中金",
    "山下火",
    "平地木",
    "壁上土",
    "金箔金",
    "覆灯火",
    "天河水",
    "大驿土",
    "钗钏金",
    "桑柘木",
    "大溪水",
    "沙中土",
    "天上火",
    "石榴木",
    "大海水",
)


def expected_keys(system):
    if system == "astro":
        groups = {
            "planet": BODIES,
            "sign": SIGNS,
            "house": map(str, range(1, 13)),
            "aspect": ASPECTS,
            "planet_sign": (f"{body}:{sign}" for body in BODIES for sign in SIGNS),
            "planet_house": (f"{body}:{house}" for body in BODIES for house in range(1, 13)),
            "transit": ["no_exact_events"],
        }
    else:
        groups = {
            "stem": GAN,
            "branch": ZHI,
            "element": WX,
            "ten_god": TEN_GODS,
            "relation": RELATIONS,
            "nayin": NAYIN,
            "god_pillar": (
                f"{god}:{pillar}" for god in TEN_GODS for pillar in ("year", "month", "day", "time")
            ),
            "hidden": ZHI,
            "element_relation": ["生", "克", "同类", "泄", "耗"],
            "convention": [
                "day_master",
                "dayun",
                "zishi_next_day",
                "zishi_same_day",
                "true_solar_time",
                "year_month_boundary",
                "unknown_time",
            ],
        }
    return {(system, kind, str(key)) for kind, keys in groups.items() for key in keys}
