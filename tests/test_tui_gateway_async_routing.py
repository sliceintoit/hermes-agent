"""Desktop async-delegation ownership fences."""

from types import SimpleNamespace

from gateway.session_context import get_session_env
from tui_gateway import server


def _session(key="key", *, agent_key=None, profile="", home="", finalized=False):
    return {
        "session_key": key,
        "agent": SimpleNamespace(session_id=agent_key or key),
        "profile": profile,
        "profile_home": home,
        "_finalized": finalized,
    }


def test_origin_ui_is_strict_return_address_even_when_key_matches():
    event = {
        "type": "async_delegation",
        "origin_ui_session_id": "origin-tab",
        "session_key": "shared-key",
    }
    foreign = _session("shared-key")
    assert server._session_owns_notification_event("foreign-tab", foreign, event) is False
    assert server._session_owns_notification_event("origin-tab", foreign, event) is True


def test_profile_fence_blocks_cross_profile_origin_match():
    event = {
        "type": "async_delegation",
        "origin_ui_session_id": "tab-1",
        "session_key": "session-1",
        "origin_profile": "highbeam",
        "origin_hermes_home": "/tmp/profiles/highbeam",
    }
    default = _session(
        "session-1", profile="default", home="/tmp/profiles/default"
    )
    assert server._session_owns_notification_event("tab-1", default, event) is False


def test_same_profile_exact_origin_owns():
    event = {
        "type": "async_delegation",
        "origin_ui_session_id": "tab-1",
        "session_key": "session-1",
        "origin_profile": "highbeam",
        "origin_hermes_home": "/tmp/profiles/highbeam",
    }
    highbeam = _session(
        "session-1", profile="highbeam", home="/tmp/profiles/highbeam"
    )
    assert server._session_owns_notification_event("tab-1", highbeam, event) is True


def test_legacy_unstamped_event_can_match_durable_key():
    event = {
        "type": "async_delegation",
        "origin_ui_session_id": "",
        "session_key": "session-1",
    }
    assert server._session_owns_notification_event(
        "any-tab", _session("session-1"), event
    ) is True


def test_empty_route_is_not_owned():
    event = {
        "type": "async_delegation",
        "origin_ui_session_id": "",
        "session_key": "",
    }
    assert server._session_owns_notification_event(
        "any-tab", _session("session-1"), event
    ) is False


def test_foreign_poller_requeues_for_live_exact_owner(monkeypatch):
    event = {
        "type": "async_delegation",
        "origin_ui_session_id": "owner-tab",
        "session_key": "owner-key",
    }
    owner = _session("owner-key")
    foreign = _session("foreign-key")
    monkeypatch.setattr(
        server,
        "_sessions",
        {"owner-tab": owner, "foreign-tab": foreign},
    )
    assert server._notification_event_belongs_elsewhere(
        "foreign-tab", foreign, event
    ) is True
    assert server._notification_event_belongs_elsewhere(
        "owner-tab", owner, event
    ) is False


def test_set_session_context_stamps_ui_and_profile(monkeypatch, tmp_path):
    sid = "desktop-tab"
    key = "durable-session"
    home = tmp_path / "profiles" / "highbeam"
    session = {
        "session_key": key,
        "cwd": str(tmp_path),
        "profile": "highbeam",
        "profile_home": str(home),
    }
    monkeypatch.setattr(server, "_sessions", {sid: session})
    tokens = server._set_session_context(
        key,
        ui_session_id=sid,
        profile="highbeam",
        profile_home=str(home),
    )
    try:
        assert get_session_env("HERMES_SESSION_SOURCE") == "desktop"
        assert get_session_env("HERMES_UI_SESSION_ID") == sid
        assert get_session_env("HERMES_SESSION_PROFILE") == "highbeam"
    finally:
        server._clear_session_context(tokens)


def test_session_create_persists_profile_route(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "august"
    profile_home.mkdir(parents=True)
    monkeypatch.setattr(
        server,
        "_profile_home",
        lambda profile: profile_home if profile == "august" else None,
    )
    monkeypatch.setattr(server, "_completion_cwd", lambda params=None: str(tmp_path))
    monkeypatch.setattr(server, "_start_agent_build", lambda *args, **kwargs: None)

    created = server._methods["session.create"](
        "route-create", {"profile": "august"}
    )
    sid = created["result"]["session_id"]
    try:
        assert server._sessions[sid]["profile"] == "august"
        assert server._sessions[sid]["profile_home"] == str(profile_home)
    finally:
        server._methods["session.close"]("route-close", {"session_id": sid})
