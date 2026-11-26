from datetime import date

import pytest

from common.birth_sampling import (
    TIME_PERIODS,
    is_valid_clock_minute,
    period_label,
    redact_sampled_time_text,
    sample_birth_time,
    sanitize_chart_for_client,
    sanitize_export_for_client,
    sanitize_reading_for_client,
)


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


@pytest.mark.parametrize("period", list(TIME_PERIODS))
def test_sample_birth_time_stays_within_period_bounds(period):
    label, start_min, end_min = TIME_PERIODS[period]
    assert period_label(period) == label
    # Ensure display label never contains digits or numeric clock ranges.
    assert not any(ch.isdigit() for ch in label)
    seen = set()
    for _ in range(150):
        hhmm = sample_birth_time(date(1995, 3, 21), period, "Asia/Shanghai")
        mins = _minutes(hhmm)
        assert start_min <= mins <= end_min
        assert is_valid_clock_minute(date(1995, 3, 21), hhmm, "Asia/Shanghai")
        seen.add(hhmm)
    # Random sampling should produce varied minutes across repeated calls.
    assert len(seen) > 10


def test_sample_birth_time_skips_dst_nonexistent_and_ambiguous_minutes():
    # China DST spring-forward: 1986-05-04 02:00-02:59 did not exist in Asia/Shanghai.
    assert not is_valid_clock_minute(date(1986, 5, 4), "02:30", "Asia/Shanghai")
    for _ in range(120):
        hhmm = sample_birth_time(date(1986, 5, 4), "early_morning", "Asia/Shanghai")
        assert is_valid_clock_minute(date(1986, 5, 4), hhmm, "Asia/Shanghai")
        assert not hhmm.startswith("02:")

    # China DST fall-back: 1986-09-14 01:00-01:59 occurred twice (ambiguous).
    assert not is_valid_clock_minute(date(1986, 9, 14), "01:30", "Asia/Shanghai")
    for _ in range(120):
        hhmm = sample_birth_time(date(1986, 9, 14), "early_morning", "Asia/Shanghai")
        assert is_valid_clock_minute(date(1986, 9, 14), hhmm, "Asia/Shanghai")
        assert not hhmm.startswith("01:")

    # US DST spring-forward & fall-back (02:00-02:59 / 01:00-01:59 in America/New_York).
    assert not is_valid_clock_minute(date(2023, 3, 12), "02:30", "America/New_York")
    assert not is_valid_clock_minute(date(2023, 11, 5), "01:30", "America/New_York")
    for dst_day, blocked_prefix in ((date(2023, 3, 12), "02:"), (date(2023, 11, 5), "01:")):
        for _ in range(120):
            hhmm = sample_birth_time(dst_day, "early_morning", "America/New_York")
            assert is_valid_clock_minute(dst_day, hhmm, "America/New_York")
            assert not hhmm.startswith(blocked_prefix)


def test_redact_sampled_time_text_covers_variants_and_preserves_conventions():
    # Standard HH:MM & Chinese variants for forenoon.
    sample = (
        "你的出生时间是 1995-03-21 09:37（上午9点37分，即09时37分），23点换日，流日精确时间 14:32。"
    )
    cleaned = redact_sampled_time_text(sample, "09:37", "forenoon")
    assert "09:37" not in cleaned
    assert "9点37" not in cleaned
    assert "09时37" not in cleaned
    assert "上午" in cleaned
    assert "上午上午" not in cleaned
    assert "23点换日" in cleaned
    assert "14:32" in cleaned

    # 12-hour afternoon Chinese phrasing for 15:42.
    pm = "你生于1995年3月21日下午3点42分（15:42），参考2026-09-30流月。"
    cleaned_pm = redact_sampled_time_text(pm, "15:42", "afternoon")
    assert "3点42" not in cleaned_pm
    assert "15:42" not in cleaned_pm
    assert "下午" in cleaned_pm
    assert "2026-09-30" in cleaned_pm

    # :30 half-hour and :00 whole-hour must NOT corrupt "23点换日" / "0点换日" / "23:00 换日".
    half = "1995年3月21日9点半出生，性格沉稳。"
    cleaned_half = redact_sampled_time_text(half, "09:30", "forenoon")
    assert "9点半" not in cleaned_half
    assert "上午" in cleaned_half

    zero_hour = "1995年3月21日23点出生，采用23点换日与23:00换日口径，0点换日不采用。"
    cleaned_zero = redact_sampled_time_text(zero_hour, "23:00", "late_night")
    assert "23点出生" not in cleaned_zero
    assert "23点换日" in cleaned_zero
    assert "23:00换日" in cleaned_zero
    assert "0点换日" in cleaned_zero

    # Unknown period removes the clock cleanly without inserting "完全不记得" mid-sentence.
    unk = "你于1995-03-21 09:37出生，日主强旺。"
    cleaned_unk = redact_sampled_time_text(unk, "09:37", "unknown")
    assert "09:37" not in cleaned_unk
    assert "1995-03-21" in cleaned_unk


def test_sanitize_chart_reading_and_export_strip_sampled_time():
    public_birth = {
        "date": "1995-03-21",
        "time": "",
        "unknown_time": True,
        "time_period": "forenoon",
        "place": "中国浙江杭州",
    }
    raw_chart = {
        "system": "bazi",
        "birth": {**public_birth, "time": "09:37", "unknown_time": False},
        "result": {
            "pillars": {"year": "乙亥", "month": "己卯", "day": "甲子", "time": "己巳"},
            "civil_time": "1995-03-21 09:37:00",
            "utc": "1995-03-21T01:37:00+00:00",
            "solar_correction_minutes": 0.0,
            "input": {"birth_local": "1995-03-21T09:37", "time_known": True},
        },
    }
    clean_chart = sanitize_chart_for_client(raw_chart, public_birth)
    assert clean_chart["birth"]["time"] == ""
    assert clean_chart["birth"]["time_period"] == "forenoon"
    assert clean_chart["result"]["input"]["birth_local"] == "1995-03-21"
    assert clean_chart["result"]["civil_time"] is None
    assert clean_chart["result"]["utc"] is None
    assert clean_chart["result"]["pillars"]["time"] == "己巳"
    # Raw dict must not be mutated.
    assert raw_chart["result"]["input"]["birth_local"] == "1995-03-21T09:37"

    raw_reading = {
        "reading_id": "r1",
        "question": "1995-03-21 09:37 性格分析",
        "output": {
            "summary": "你生于1995年3月21日上午09:37，整体偏稳。",
            "sections": [{"title": "性格", "body": "9点37分对应的命局偏细致。", "ref_ids": []}],
            "advice": ["结合09:37看可循序渐进。"],
            "closing": "祝好。",
        },
        "calculations": {"bazi_result": raw_chart["result"]},
        "birth_context": {"version": 1, "birth": public_birth, "_sampled_time": "09:37"},
        "responses": [{"question": "追问", "output": {"summary": "复核09:37无误。"}}],
    }
    clean_reading = sanitize_reading_for_client(raw_reading)
    assert "_sampled_time" not in clean_reading["birth_context"]
    assert "09:37" not in str(clean_reading)
    assert "9点37" not in str(clean_reading)
    assert "上午" in clean_reading["output"]["summary"]

    export_payload = {
        "birth": dict(public_birth),
        "profile": {"birth_local_dt": "1995-03-21 09:37", "time_known": True, "version": 1},
        "profile_history": [
            {
                "version": 1,
                "profile": {"birth_local_dt": "1995-03-21 09:37", "time_known": True},
                "evidence": "我的出生日期是公历 1995-03-21 上午；出生地点是中国浙江杭州",
                "updated_at": "2026-11-26T00:00:00+00:00",
            }
        ],
        "readings": [raw_reading],
    }
    clean_export = sanitize_export_for_client(
        export_payload, {"date": "1995-03-21", "time_period": "forenoon", "resolved_time": "09:37"}
    )
    assert "09:37" not in str(clean_export)
    assert "9点37" not in str(clean_export)
    assert clean_export["birth"]["time_period"] == "forenoon"
    assert clean_export["birth"]["time_period_label"] == "上午"
    assert clean_export["profile"]["birth_local_dt"] == "1995-03-21"
    assert clean_export["profile"]["time_period_label"] == "上午"
    assert clean_export["profile_history"][0]["profile"]["birth_local_dt"] == "1995-03-21"
    assert clean_export["profile_history"][0]["profile"]["time_period_label"] == "上午"
