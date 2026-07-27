"""Capture the exact async completion return address before dispatch."""

from types import SimpleNamespace

from tools.approval import reset_current_session_key, set_current_session_key
from tools.delegate_tool import _capture_async_delegation_route


def test_desktop_route_prefers_durable_agent_session_over_approval_key():
    agent = SimpleNamespace(
        session_id="durable-after-compression",
        _hermes_ui_session_id="desktop-tab-9",
        _hermes_session_profile="highbeam",
        _hermes_home="/tmp/profiles/highbeam",
    )
    token = set_current_session_key("stale-before-compression")
    try:
        route = _capture_async_delegation_route(agent)
    finally:
        reset_current_session_key(token)

    assert route == {
        "session_key": "durable-after-compression",
        "parent_session_id": "durable-after-compression",
        "origin_ui_session_id": "desktop-tab-9",
        "origin_profile": "highbeam",
        "origin_hermes_home": "/tmp/profiles/highbeam",
    }


def test_gateway_route_without_ui_stamp_keeps_platform_session_key():
    agent = SimpleNamespace(session_id="agent-db-id", _hermes_home="/tmp/hermes")
    token = set_current_session_key("agent:main:telegram:dm:42")
    try:
        route = _capture_async_delegation_route(agent)
    finally:
        reset_current_session_key(token)

    assert route["session_key"] == "agent:main:telegram:dm:42"
    assert route["parent_session_id"] == "agent-db-id"
    assert route["origin_ui_session_id"] == ""
