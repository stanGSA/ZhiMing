MAJOR = [
    ("the_fool", "愚人"),
    ("the_magician", "魔术师"),
    ("the_high_priestess", "女祭司"),
    ("the_empress", "皇后"),
    ("the_emperor", "皇帝"),
    ("the_hierophant", "教皇"),
    ("the_lovers", "恋人"),
    ("the_chariot", "战车"),
    ("strength", "力量"),
    ("the_hermit", "隐者"),
    ("wheel_of_fortune", "命运之轮"),
    ("justice", "正义"),
    ("the_hanged_man", "倒吊人"),
    ("death", "死神"),
    ("temperance", "节制"),
    ("the_devil", "恶魔"),
    ("the_tower", "高塔"),
    ("the_star", "星星"),
    ("the_moon", "月亮"),
    ("the_sun", "太阳"),
    ("judgement", "审判"),
    ("the_world", "世界"),
]
SUITS = [("wands", "权杖"), ("cups", "圣杯"), ("swords", "宝剑"), ("pentacles", "星币")]
RANKS = [
    ("ace", "一"),
    ("two", "二"),
    ("three", "三"),
    ("four", "四"),
    ("five", "五"),
    ("six", "六"),
    ("seven", "七"),
    ("eight", "八"),
    ("nine", "九"),
    ("ten", "十"),
    ("page", "侍从"),
    ("knight", "骑士"),
    ("queen", "王后"),
    ("king", "国王"),
]
DECK = MAJOR + [
    (f"{suit}_{rank}", f"{label}{rank_label}")
    for suit, label in SUITS
    for rank, rank_label in RANKS
]
SPREADS = {
    "single": ["当下提示"],
    "three_card": ["过去", "现在", "未来"],
    "decision": ["现状", "选 A", "选 B"],
}
