import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.agent_runtime_helpers import invoke_tool
from agent.tool_executor import _tool_search_scoped_names


def _agent(enabled_toolsets):
    return SimpleNamespace(
        enabled_toolsets=enabled_toolsets,
        disabled_toolsets=None,
        session_id="current-session",
        _current_turn_id="turn-1",
        _current_api_request_id="request-1",
        _get_session_db_for_recall=lambda: object(),
    )


def test_invoke_tool_unwraps_deferred_session_search_before_agent_dispatch():
    agent = _agent(["session_search"])
    expected = json.dumps({"success": True, "mode": "discover", "count": 1})

    with patch("tools.session_search_tool.session_search", return_value=expected) as search:
        result = invoke_tool(
            agent,
            "tool_call",
            {"name": "session_search", "arguments": {"query": "GitHub", "limit": 1}},
            "task-1",
            tool_call_id="call-1",
            pre_tool_block_checked=True,
            skip_tool_request_middleware=True,
        )

    assert result == expected
    search.assert_called_once_with(
        query="GitHub",
        role_filter=None,
        limit=1,
        session_id=None,
        around_message_id=None,
        window=5,
        sort=None,
        db=search.call_args.kwargs["db"],
        current_session_id="current-session",
    )


def test_invoke_tool_keeps_deferred_tool_scope_closed():
    result = json.loads(invoke_tool(
        _agent(["session_search"]),
        "tool_call",
        {"name": "clarify", "arguments": {"question": "Continue?"}},
        "task-1",
        pre_tool_block_checked=True,
        skip_tool_request_middleware=True,
    ))

    assert "not available in this session" in result["error"]


def test_executor_scope_includes_curated_deferred_core_tools():
    names = _tool_search_scoped_names(_agent(["session_search"]))

    assert "session_search" in names


def test_executor_scope_excludes_ungranted_curated_tools():
    names = _tool_search_scoped_names(_agent(["session_search"]))

    assert "clarify" not in names


def test_executor_scope_includes_deferred_skill_manage_only_when_granted():
    assert "skill_manage" in _tool_search_scoped_names(_agent(["skills"]))
    assert "skill_manage" not in _tool_search_scoped_names(_agent(["session_search"]))
