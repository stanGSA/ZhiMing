"""A live case's profile is saved before the runtime that answers it (P2 daily)."""

from app import create_runtime
from scripts import live_week23

BIRTH = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "Asia/Shanghai",
    "lat": 30.66,
    "lon": 104.07,
    "time_known": True,
}


def test_the_answering_runtime_starts_from_the_case_profile(project, monkeypatch):
    created = []

    def demo(root, user_id, model_name, mode):
        runtime = create_runtime(root=project, user_id=user_id, mode=mode)
        created.append(runtime)
        return runtime

    monkeypatch.setattr(live_week23, "create_runtime", demo)
    runtime = live_week23.start_runtime(project, "returning-user", "any", "single", BIRTH)
    try:
        assert {k: runtime.session.profile[k] for k in BIRTH} == BIRTH
        assert runtime.session.calendar_timezone == "Asia/Shanghai"
        # The memory note the model reads was written from the saved profile.
        assert any("1996-05-10" in m["content"] for m in runtime.session.messages[:3])
        assert len(created) == 2
    finally:
        runtime.close()
    plain = live_week23.start_runtime(project, "new-user", "any", "single")
    try:
        assert "birth_local_dt" not in plain.session.profile and len(created) == 3
    finally:
        plain.close()
