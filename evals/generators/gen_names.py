"""Generate evals/cases/name_strokes.yaml (200 characters).

Rule (五格剖象法 convention): 康熙笔画 = 康熙部首的原字笔画 + 余笔
  - 繁体字形取自 Unihan kTraditionalVariant（姓氏有专门覆盖表）
  - 部首与余笔取自 Unihan kRSUnicode（第一个值）；氵按水 4 画、扌按手 4 画、
    艹按艸 6 画、辶按辵 7 画、左阝按阜 8 画、右阝按邑 7 画、王字旁按玉 5 画……
    都由“部首原字笔画”自动体现
  - 数字一至十按数值计笔画（五格惯例）
Cross-check: kTotalStrokes（现代笔画）、一组公认的常见姓氏五格笔画。
"""
import os
import sys
import unicodedata
import yaml

U = os.environ.get("UNIHAN_DIR", "data/unihan")  # 含 kRSUnicode.txt 等单字段文件
OUT = sys.argv[1]


def load(field):
    d = {}
    for line in open(f"{U}/{field}.txt", encoding="utf-8"):
        if not line.strip() or line.startswith("#"):
            continue
        cp, val = line.rstrip("\n").split("\t", 1)
        if ".." in cp:
            a, b = (int(x, 16) for x in cp.split(".."))
            for c in range(a, b + 1):
                d[chr(c)] = val
        else:
            d[chr(int(cp, 16))] = val
    return d


RS = load("kRSUnicode")
TOTAL = load("kTotalStrokes")
TRAD = load("kTraditionalVariant")
KANGXI = load("kKangXi")


def radical_strokes(n):
    for hi, s in ((6, 1), (29, 2), (60, 3), (94, 4), (117, 5), (146, 6), (166, 7), (175, 8), (186, 9),
                  (194, 10), (200, 11), (204, 12), (208, 13), (210, 14), (211, 15), (213, 16), (214, 17)):
        if n <= hi:
            return s


def radical_char(n):
    return unicodedata.normalize("NFKC", chr(0x2F00 + n - 1))


SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈"
                "姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤")
GIVEN = list("伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂华玉萍红鹏辉建文浩宇子欣怡思雨晨博轩梓涵诗琪佳嘉瑶婷雪慧晴悦宁安泽俊毅凯睿"
             "一二三四五六七八九十琳瑞芝茜莉蕊荣远达道迪郁邦都阳隆胜朋清恒祥福礼裕绮振心永美婉彬")

# 姓氏的繁体写法与通用简繁转换不同的情况（姓氏用字惯例）
SURNAME_TRAD_OVERRIDE = {
    "于": ("于", "姓氏“于”不转写为“於”"),
    "余": ("余", "姓氏“余”不转写为“餘”"),
    "范": ("范", "姓氏“范”不转写为“範”"),
    "姜": ("姜", "姓氏“姜”不转写为“薑”"),
    "钟": ("鍾", "姓氏多写作“鍾”，而不是“鐘”"),
    "肖": ("肖", "大陆身份证多写“肖”；港台多写“蕭”（20 画），需按用户实际写法确认"),
    "叶": ("葉", "姓氏“叶”繁体为“葉”"),
    "胡": ("胡", "姓氏“胡”不转写为“衚”“鬍”"),
    "朱": ("朱", "姓氏“朱”不转写为“硃”"),
    "沈": ("沈", "姓氏“沈”不转写为“瀋”"),
    "向": ("向", "姓氏“向”不转写为“嚮”“曏”"),
    "苏": ("蘇", "姓氏“苏”繁体为“蘇”，不是“囌”"),
    "万": ("萬", "姓氏“万”繁体多写“萬”（15 画）；复姓“万俟”保留“万”，需确认"),
}
GIVEN_AMBIGUOUS = {
    "杰": "名字中“杰”常保留原字（8 画），也有人写“傑”（12 画）",
    "郁": "名字中“郁”多为本字（13 画），简繁转换会映射到“鬱”（29 画）",
    "强": "“强”与“強”是异体，笔画分别为 12 与 11，各家五格书取法不一",
    "胜": "“胜”在名字里多对应“勝”（12 画），但“胜”本身也是独立字（肉部 9 画）",
    "艳": "“艳”的繁体有“豔”“艷”两种写法，笔画不同",
    "丽": "简繁转换“麗”是常规，但个别人身份证件写“丽”",
}
GIVEN_TRAD_OVERRIDE = {"郁": "郁"}
# 公认的常见姓氏五格笔画（用于校验规则实现是否正确）
KNOWN = {"王": 4, "李": 7, "张": 11, "刘": 15, "陈": 16, "杨": 13, "黄": 12, "赵": 14, "吴": 7, "周": 8,
         "徐": 10, "孙": 10, "马": 10, "朱": 6, "胡": 11, "郭": 15, "何": 7, "高": 10, "林": 8, "罗": 20,
         "郑": 19, "梁": 11, "谢": 17, "宋": 7, "唐": 10, "许": 11, "韩": 17, "冯": 12, "邓": 19, "曹": 11,
         "彭": 12, "曾": 12, "江": 7, "陆": 16, "范": 11, "董": 15, "潘": 16}
NUMERALS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def entry(ch, role):
    reasons, rules = [], []
    if role == "surname" and ch in SURNAME_TRAD_OVERRIDE:
        trad, why = SURNAME_TRAD_OVERRIDE[ch]
        rules.append("姓氏繁体覆盖")
        reasons.append(why)
    elif role == "given" and ch in GIVEN_TRAD_OVERRIDE:
        trad = GIVEN_TRAD_OVERRIDE[ch]
        rules.append("名字用字繁体覆盖")
    else:
        tv = TRAD.get(ch)
        if tv:
            opts = [chr(int(x[2:], 16)) for x in tv.split()]
            others = [o for o in opts if o != ch]
            trad = others[0] if others else ch
            if len(others) > 1:
                reasons.append("Unihan 给出多个繁体：" + "、".join(others) + f"，默认取“{trad}”")
        else:
            trad = ch
    if ch in GIVEN_AMBIGUOUS and role == "given":
        reasons.append(GIVEN_AMBIGUOUS[ch])
    rs_all = RS[trad].split()
    rs = rs_all[0]
    if len(rs_all) > 1:
        cand = {v: radical_strokes(int(v.split(".")[0].replace("'", ""))) + int(v.split(".")[1]) for v in rs_all}
        restoring = {140, 162, 170, 163, 85, 64, 61, 94, 113, 145, 130, 96}
        pref = [v for v in rs_all if int(v.split(".")[0].replace("'", "")) in restoring]
        rs = pref[0] if pref else rs_all[0]
        if len(set(cand.values())) > 1:
            reasons.append("Unihan 给出多个部首归属：" + "、".join(f"{v}→{n} 画" for v, n in cand.items())
                           + f"，按康熙字典习惯取 {rs}")
    rad_s, res_s = rs.split(".")
    simplified_radical = "'" in rad_s
    rad = int(rad_s.replace("'", ""))
    res = int(res_s)
    if simplified_radical:
        reasons.append("部首是简化部首，说明繁体映射可能失败")
    rstrokes = radical_strokes(rad)
    strokes = rstrokes + res
    rules.append(f"部首还原：{radical_char(rad)}（第 {rad} 部，{rstrokes} 画）+ 余笔 {res}")
    if ch in NUMERALS:
        strokes = NUMERALS[ch]
        rules.append(f"数字按数值计：{strokes}")
    modern_trad = int(TOTAL.get(trad, "0").split()[0])
    item = {
        "char": ch,
        "role": role,
        "traditional": trad,
        "kRSUnicode": rs,
        "radical": {"number": rad, "char": radical_char(rad), "strokes": rstrokes},
        "residual_strokes": res,
        "expected_kangxi_strokes": strokes,
        "modern_strokes": {"simplified": int(TOTAL[ch].split()[0]), "traditional": modern_trad},
        "rules_applied": rules,
        "in_kangxi_dictionary": trad in KANGXI,
    }
    if strokes != modern_trad:
        item["differs_from_modern_traditional_count"] = True
    if ch in KNOWN:
        item["known_value"] = KNOWN[ch]
        if KNOWN[ch] != strokes:
            reasons.append(f"与公认值 {KNOWN[ch]} 不一致")
    item["status"] = "needs_review" if reasons else "auto_ok"
    if reasons:
        item["review_reasons"] = reasons
    return item


assert len(set(SURNAMES)) == len(SURNAMES), "dup surname"
assert len(set(GIVEN)) == len(GIVEN), "dup given"
assert not set(SURNAMES) & set(GIVEN), set(SURNAMES) & set(GIVEN)
print(len(SURNAMES), len(GIVEN))
items = [entry(c, "surname") for c in SURNAMES] + [entry(c, "given") for c in GIVEN]
items = [{"id": f"name-{k:03d}", **it} for k, it in enumerate(items, 1)]
known_ok = sum(1 for i in items if "known_value" in i and i["known_value"] == i["expected_kangxi_strokes"])
known_n = sum(1 for i in items if "known_value" in i)

doc = {
    "dataset": "name_strokes",
    "version": 1,
    "purpose": "姓名五格的康熙笔画测试：100 个常见姓氏用字 + 100 个常见名字用字，覆盖部首还原、数字、姓氏繁体惯例等规则",
    "generated_with": {
        "source": "Unicode Unihan 18.0（unicode-org/unicodetools 仓库）：kTraditionalVariant、kRSUnicode、kTotalStrokes、kKangXi",
        "rule": "康熙笔画 = 部首原字笔画 + 余笔；数字一至十按数值；姓氏繁体按姓氏惯例覆盖",
        "cross_check": f"与 {known_n} 个公认常见姓氏五格笔画比对：{known_ok}/{known_n} 一致",
    },
    "summary": {
        "items": len(items),
        "auto_ok": sum(1 for i in items if i["status"] == "auto_ok"),
        "needs_review": sum(1 for i in items if i["status"] == "needs_review"),
    },
    "how_to_use": [
        "auto_ok：规则计算结果，可直接作为期望值。",
        "needs_review：存在繁体写法歧义或流派差异；评估时期望行为是工具给出默认值并在 notes 里提示，或通过 ask_user 让用户确认写法。上线前请人工对照康熙字典定稿。",
        "五格笔画本身是民间约定，不同书籍对少数字有分歧；本数据集的标准答案就是上面这条规则，项目实现若采用别的约定，需要同步修改。",
    ],
    "items": items,
}
from yamlio import dump
dump(doc, OUT)
print(doc["generated_with"]["cross_check"], doc["summary"])
for i in items:
    if i["status"] == "needs_review":
        print(i["char"], i["traditional"], i["expected_kangxi_strokes"], i["review_reasons"])
