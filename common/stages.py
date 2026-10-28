"""Model tool visibility; Guard continues to validate calls independently."""

from dataclasses import replace


def available(tool, session):
    state = session.state
    name = tool.name
    if session.role == "reviewer":
        return True
    if state.get("response_mode") == "followup" and not state.get("complete"):
        return name in {"read_reading", "lookup_meaning", "submit_reading"}
    if name in {
        "get_profile",
        "update_profile",
        "start_reading",
        "read_reading",
        "resolve_location",
        "ask_user",
    }:
        return True
    if not state.get("active_reading_id"):
        return False
    if tool.dependency and not state.get(tool.dependency):
        return False
    systems = state.get("systems")
    if tool.partition and systems and tool.partition not in systems:
        return False
    if name in {"submit_reading", "submit_report", "lookup_meaning"}:
        if name == "lookup_meaning" and state.get("bazi_result"):
            from plugins.bazi.intent import dayun_overview_state

            if dayun_overview_state(state) and {s["system"] for s in state.get("signals", [])} == {
                "bazi"
            }:
                # All cycle facts and their meanings are already present. Free-form
                # lookup caused the production request to spend four rounds guessing keys.
                return False
        return bool(state.get("signals"))
    if name == "merge_signals":
        return len({s["system"] for s in state.get("signals", [])}) >= 2
    return True


def install(registry):
    for name, tool in list(registry.tools.items()):
        previous = tool.available

        def predicate(session, tool=tool, previous=previous):
            return (previous is None or previous(session)) and available(tool, session)

        # Lookup/report tools can be shared across specialist registries.
        registry.tools[name] = replace(tool, available=predicate)
