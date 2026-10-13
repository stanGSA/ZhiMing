"""Conservative deterministic normalization; retain source evidence separately."""

import calendar
import re
from datetime import date, datetime

DATE = r"(?<!\d)(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})日?(?!\d)"
NUMBER = r"[零〇一二两三四五六七八九十\d]+"


def chinese_number(value):
    if value.isdigit():
        return int(value)
    digits = dict(
        zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9), strict=True)
    )
    if "十" in value:
        a, b = value.split("十", 1)
        return digits.get(a, 1) * 10 + digits.get(b, 0)
    return digits.get(value, -1)


def clock_in(text):
    match = re.search(
        rf"(凌晨|早上|上午|中午|下午|晚上|晚间)?\s*({NUMBER})(?:[:：]|点|时)\s*([一三1３3]刻|半|{NUMBER})?",
        text,
    )
    if not match:
        return None
    if re.search(
        r"大约|大概|约|差不多", text[max(0, match.start() - 5) : match.start()]
    ) or re.match(r"(?:分)?\s*(?:多|左右|上下|前后|许|附近)", text[match.end() :]):
        return None  # An approximate hour is not evidence for an exact clock time.
    period, hour, minute = match.groups()
    hour = chinese_number(hour)
    minute = (
        30
        if minute == "半"
        else 15 * chinese_number(minute[:-1])
        if minute and minute.endswith("刻")
        else chinese_number(minute or "0")
    )
    if period in ("下午", "晚上", "晚间") and 1 <= hour < 12:
        hour += 12
    if period in ("凌晨", "晚上", "晚间") and hour == 12:
        hour = 0
    if period == "中午" and 1 <= hour <= 2:
        hour += 12
    return f"{hour:02d}:{minute:02d}" if 0 <= hour < 24 and 0 <= minute < 60 else None


def birth_mentions(text):
    matches = list(re.finditer(DATE, text))
    found = []
    for i, match in enumerate(matches):
        try:
            day = date(*map(int, match.groups())).isoformat()
        except ValueError:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # Do not associate a later sentence's time with this date.
        tail = re.split(r"[。；;\n]", text[match.end() : end], maxsplit=1)[0]
        found.append((day, clock_in(tail)))
    return found


def supported_birth(value, text, time_known=True):
    try:
        value = datetime.fromisoformat(value.replace("T", " ")).isoformat(sep=" ")
    except (ValueError, TypeError):
        return False
    return any(
        day == value[:10] and (not time_known or clock == value[11:16])
        for day, clock in birth_mentions(text)
    )


def normalized_gender(value):
    return {
        "男": "male",
        "男性": "male",
        "male": "male",
        "女": "female",
        "女性": "female",
        "female": "female",
    }.get(str(value).strip().lower())


def gender_evidence(text):
    result = set()
    for match in re.finditer(r"男性|女性|男|女|\bmale\b|\bfemale\b", text, re.I):
        if re.search(r"不是|并非|非", text[max(0, match.start() - 3) : match.start()]):
            continue
        result.add(normalized_gender(match.group()))
    return result


def solar_time_choice(text):
    """Return a confirmed choice, never interpret a bare keyword or a question as consent."""
    if re.search(r"还是|(?:是否|要不要|能否).{0,6}真太阳时|真太阳时[吗？?]", text):
        return None
    if re.search(r"不是不|并非不", text):
        return None
    negative = r"(?:不(?:要)?(?:使用|采用|用|按)|关闭|不开启|无需)\s*真太阳时|(?:按)?\s*固定\s*UTC\s*\+\s*8|按北京时间"
    positive = r"(?:使用|采用|启用|开启|按|用)\s*真太阳时"
    no = bool(re.search(negative, text, re.I))
    yes = bool(re.search(positive, re.sub(negative, "", text, flags=re.I)))
    return (not no) if no != yes else None


def question_range(text, anchor=None):
    """Only linked dates are a range; an unrelated birth date never becomes an endpoint."""
    match = re.search(DATE + r"\s*(?:至|到|—|~|～|–)\s*" + DATE, text)
    if match:
        try:
            values = list(map(int, match.groups()))
            return date(*values[:3]).isoformat(), date(*values[3:]).isoformat()
        except ValueError:
            return None
    # Remove birth dates before looking for a month request.
    cleaned = re.sub(DATE, "", text)
    month = re.search(r"(\d{4})年(\d{1,2})月", cleaned)
    if month:
        year, month = map(int, month.groups())
    elif anchor and re.search(r"下下个月|下个月|本月|这个月|上上个月|上个月", cleaned):
        current = date.fromisoformat(anchor)
        phrase = re.search(r"下下个月|下个月|本月|这个月|上上个月|上个月", cleaned)[0]
        offset = {"下下个月": 2, "下个月": 1, "上上个月": -2, "上个月": -1}.get(phrase, 0)
        year, index = divmod(current.year * 12 + current.month - 1 + offset, 12)
        month = index + 1
    else:
        return None
    if not 1 <= month <= 12:
        return None
    return (
        f"{year:04d}-{month:02d}-01",
        f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}",
    )


def reading_text(session):
    index = session.state.get("question_message_index", 0)
    return " ".join(session.user_messages[index:])
