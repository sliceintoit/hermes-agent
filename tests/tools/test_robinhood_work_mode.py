"""Real resolution/dispatch paths with a synthetic, isolated MCP registry."""
import json

import pytest

import model_tools
from tools.registry import registry
from tools.tool_search import dispatch_tool_search, unavailable_tool_result
from toolsets import resolve_toolset
from tui_gateway.work_modes import toolsets_for_work_mode, validate_work_mode_readiness

MARKET = set(resolve_toolset("robinhood_research"))
HISTORY = "mcp_robinhood_get_equity_historicals"
FORBIDDEN = {"mcp_robinhood_get_portfolio", "mcp_robinhood_get_equity_positions",
             "mcp_robinhood_place_equity_order", "mcp_robinhood_future_unknown_tool"}


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setattr(registry, "_tools", dict(registry._tools))
    model_tools._tool_defs_cache.clear()
    calls = []
    for name in MARKET | FORBIDDEN:
        registry.register(
            name=name, toolset="mcp-robinhood",
            schema={"name": name, "description": "Test market tool",
                    "parameters": {"type": "object", "properties": {}}},
            handler=lambda args, **kw: calls.append(args) or '{"ok": true}',
        )
    yield calls
    model_tools._tool_defs_cache.clear()


def raw_defs(mode):
    return model_tools.get_tool_definitions(
        enabled_toolsets=list(toolsets_for_work_mode(mode) or ()),
        quiet_mode=True, skip_tool_search_assembly=True,
    )


def test_research_is_exact_market_allowlist_and_everyday_stays_lean(registered):
    research = {td["function"]["name"] for td in raw_defs("robinhood_research")}
    everyday = {td["function"]["name"] for td in raw_defs("everyday")}
    assert {n for n in research if n.startswith("mcp_")} == MARKET
    assert not research & FORBIDDEN
    assert not everyday & MARKET
    assert {"terminal", "read_file", "write_file"} <= research


@pytest.mark.parametrize("bridge", ["tool_call", "tool_describe"])
def test_out_of_scope_has_action_and_never_calls_server(registered, bridge):
    result = json.loads(model_tools.handle_function_call(
        bridge, {"name": HISTORY, "arguments": {}}, enabled_toolsets=["core"],
    ))
    assert result["status"] == "out_of_scope"
    assert result["suggested_work_mode"] == "robinhood_research"
    assert not registered


def test_unknown_registration_still_explains_scope():
    result = unavailable_tool_result(HISTORY, [], ["core"])
    assert result["status"] == "out_of_scope"
    assert "Robinhood Research" in result["action"]
    result = unavailable_tool_result(HISTORY, [], ["robinhood_research"])
    assert result["status"] == "unavailable"


def test_direct_only_when_in_current_definitions():
    result = unavailable_tool_result("terminal", [{"function": {"name": "terminal"}}], ["core"])
    assert result["status"] == "direct"


def test_explicitly_disabled_scope_is_not_a_connection_failure(registered):
    result = json.loads(model_tools.handle_function_call(
        "tool_call", {"name": HISTORY, "arguments": {}},
        enabled_toolsets=["robinhood_research"], disabled_toolsets=["mcp-robinhood"],
    ))
    assert result["status"] == "out_of_scope"
    assert not registered


def test_search_suggests_new_mode_without_exposing_schema(registered):
    result = json.loads(dispatch_tool_search(
        {"query": "Robinhood historicals"}, current_tool_defs=raw_defs("everyday"),
        enabled_toolsets=["core"],
    ))
    assert result["matches"] == []
    assert result["availability"][0]["suggested_work_mode"] == "robinhood_research"
    assert "parameters" not in json.dumps(result)


def test_research_describe_works_but_holdings_are_blocked(registered):
    selected = list(toolsets_for_work_mode("robinhood_research") or ())
    result = json.loads(model_tools.handle_function_call(
        "tool_describe", {"name": HISTORY}, enabled_toolsets=selected,
    ))
    assert result["name"] == HISTORY
    for name in FORBIDDEN:
        result = json.loads(model_tools.handle_function_call(
            "tool_call", {"name": name, "arguments": {}}, enabled_toolsets=selected,
        ))
        assert result["status"] == "out_of_scope"
    assert not registered


def test_readiness_distinguishes_config_connection_and_filters(monkeypatch, registered):
    from hermes_cli import config
    from tools import mcp_tool
    monkeypatch.setattr(config, "load_config", lambda: {})
    with pytest.raises(ValueError, match="configured, enabled"):
        validate_work_mode_readiness("robinhood_research")
    monkeypatch.setattr(config, "load_config", lambda: {"mcp_servers": {"robinhood": {}}})
    monkeypatch.setattr(mcp_tool, "get_mcp_status", lambda: [])
    with pytest.raises(ValueError, match="disconnected"):
        validate_work_mode_readiness("robinhood_research")
    monkeypatch.setattr(mcp_tool, "get_mcp_status", lambda: [{"name": "robinhood", "connected": True}])
    validate_work_mode_readiness("robinhood_research")
    monkeypatch.delitem(registry._tools, HISTORY)
    model_tools._tool_defs_cache.clear()
    with pytest.raises(ValueError, match="tool filter"):
        validate_work_mode_readiness("robinhood_research")
    validate_work_mode_readiness("everyday")
