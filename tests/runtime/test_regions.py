import pytest

from common.location import Gazetteer, LocationInput, birth_place_mentioned, location_tool
from common.regions import region_data, region_options, selected_region
from common.time_utils import NeedsInput
from harness.session import Session
from memory.store import Store
from plugins.context import BirthInput, birth_provenance, birth_values


def test_county_resolves_from_user_evidence_without_substituting_city():
    gazetteer = Gazetteer()
    args = LocationInput(query="临泉县", country="CN", admin1="安徽省", candidate_id="1803361")
    session = Session(user_id="region-test")
    session.append_user("出生地为中国 · 安徽省 · 阜阳市 · 临泉县，地点编号1803361")
    tool = location_tool(gazetteer)
    assert tool.validator(args, session) is None
    result = tool.handler(args, session)
    assert result["status"] == "resolved"
    assert result["location"]["name"] == "临泉县"
    assert result["location"]["lon"] == 115.32038
    assert result["location"]["tz"] == "Asia/Shanghai"
    assert (
        gazetteer.resolve(LocationInput(query="中国 · 安徽省 · 阜阳市 · 临泉县"))["location"]
        == result["location"]
    )


def test_resolved_birth_location_is_saved_by_code(tmp_path):
    store = Store(tmp_path / "memory.sqlite")
    session = Session(user_id="birth-location")
    session.append_user("我出生在北京，请用八字看看性格。")
    tool = location_tool(Gazetteer(), store)
    args = LocationInput(query="北京")
    assert tool.validator(args, session) is None
    result = tool.handler(args, session)
    assert result["status"] == "resolved"
    saved = store.get_profile(session.user_id)
    assert saved["birth_place"] == "北京"
    assert saved["location_id"] == result["location"]["location_id"]
    assert saved["tz"] == result["location"]["tz"]
    assert saved["lat"] == result["location"]["lat"]
    assert saved["lon"] == result["location"]["lon"]
    store.close()


@pytest.mark.parametrize(
    "message,place,expected",
    [
        ("我在北京出生，现在住在纽约，咨询按纽约时间。", "北京", True),
        ("我在北京出生，现在住在纽约，咨询按纽约时间。", "纽约", False),
        ("我在北京出生现在住在纽约", "纽约", False),
        ("我住在纽约，1993年出生于北京", "纽约", False),
        ("出生在北京，后来去了纽约", "纽约", False),
        ("我是男，出生于1993-08-17 23:20，北京；用于合成测试。", "北京", True),
        ("出生地点是中国浙江杭州", "杭州", True),
        ("我记错了，我其实是在美国纽约出生的", "纽约", True),
    ],
)
def test_only_the_named_birthplace_is_birth_evidence(message, place, expected):
    assert birth_place_mentioned(message, place) is expected


def test_residence_is_not_saved_as_birthplace(tmp_path):
    store = Store(tmp_path / "memory.sqlite")
    session = Session(user_id="residence")
    session.append_user("我是男性，1993年8月17日23点20分在北京出生，现在住在纽约，咨询按纽约时间。")
    tool = location_tool(Gazetteer(), store)
    for query in ("北京", "纽约"):
        args = LocationInput(query=query)
        assert tool.validator(args, session) is None
        assert tool.handler(args, session)["status"] == "resolved"
    saved = store.get_profile(session.user_id)
    assert saved["birth_place"] == "北京"
    assert saved["tz"] == "Asia/Shanghai"
    store.close()


def test_xinjiang_birthplace_never_saves_an_unconfirmed_clock(tmp_path):
    store = Store(tmp_path / "memory.sqlite")
    session = Session(user_id="xinjiang")
    # A clock saved for an earlier birthplace must not answer for the new one.
    session.profile = store.update_profile(session.user_id, "tz", "Asia/Shanghai", "旧资料")
    session.append_user("合成资料：2000-01-01 10:00，乌鲁木齐出生，分析工作方向。")
    tool = location_tool(Gazetteer(), store)
    args = LocationInput(query="乌鲁木齐")
    assert tool.handler(args, session)["status"] == "resolved"
    saved = store.get_profile(session.user_id)
    assert saved["birth_place"] == "乌鲁木齐"
    assert saved["tz"] is None
    session.append_user("我确认使用北京时间。")
    tool.handler(args, session)
    assert store.get_profile(session.user_id)["tz"] == "Asia/Shanghai"
    store.close()


def test_xinjiang_clock_ignores_choices_before_birthplace_correction(tmp_path):
    store = Store(tmp_path / "memory.sqlite")
    session = Session(user_id="corrected-birthplace")
    tool = location_tool(Gazetteer(), store)
    session.append_user("我在北京出生，出生钟表用北京时间。")
    tool.handler(LocationInput(query="北京"), session)
    session.append_user("出生地记错了，我其实在乌鲁木齐出生，时间不变。")
    location = tool.handler(LocationInput(query="乌鲁木齐"), session)["location"]
    assert store.get_profile(session.user_id)["tz"] is None
    birth = BirthInput(location_id=location["location_id"])
    with pytest.raises(NeedsInput) as missing:
        birth_values(birth, session)
    assert missing.value.code == "confirm_clock_timezone"
    old_clock = birth.model_copy(update={"tz": "Asia/Shanghai"})
    assert birth_provenance(old_clock, session)
    with pytest.raises(NeedsInput) as missing:
        birth_values(old_clock, session)
    assert missing.value.code == "confirm_clock_timezone"
    # The later answer overrides the older clock instead of creating a conflict.
    session.append_user("我确认出生钟表用新疆时间。")
    assert birth_values(birth, session)["tz"] == "Asia/Urumqi"
    tool.handler(LocationInput(query="乌鲁木齐"), session)
    assert store.get_profile(session.user_id)["tz"] == "Asia/Urumqi"
    store.close()


def test_xinjiang_confirmed_clock_survives_a_new_session(tmp_path):
    store = Store(tmp_path / "memory.sqlite")
    session = Session(user_id="saved-xinjiang-clock")
    tool = location_tool(Gazetteer(), store)
    session.append_user("乌鲁木齐出生，出生钟表用北京时间。")
    location = tool.handler(LocationInput(query="乌鲁木齐"), session)["location"]
    later = Session(user_id=session.user_id, profile=store.get_profile(session.user_id))
    later.append_user("请用我的出生资料看工作方向。")
    tool.handler(LocationInput(query="乌鲁木齐"), later)
    assert store.get_profile(session.user_id)["tz"] == "Asia/Shanghai"
    assert birth_values(BirthInput(location_id=location["location_id"]), later)["tz"] == (
        "Asia/Shanghai"
    )
    store.close()


def test_hierarchy_integrity_and_foreign_city_scope():
    data = region_data()
    nodes = data["nodes"]
    assert len(region_options("CN")) == 31
    assert sum(n["level"] == "district" for n in nodes.values()) >= 2900
    for node in nodes.values():
        if node["parent"] is not None:
            assert node["parent"] in nodes
            assert node["parent"] != node["id"]
        if location := node.get("location"):
            assert -90 < location["lat"] < 90
            assert -180 <= location["lon"] <= 180
            assert location["tz"]
    new_york = selected_region("5128581")
    assert new_york["country"] == "US"
    assert new_york["tz"] == "America/New_York"
    assert region_options("5128581") == []
    assert data["metadata"]["license"] == "CC BY 4.0"
