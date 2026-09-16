"""Session-scoped Desktop work-mode definitions.

A work mode is selected before a TUI/Desktop agent is built.  It fixes the
agent's toolset for the lifetime of that conversation, preserving prompt-cache
stability.  The selection is stored in the session's existing ``model_config``
JSON metadata and restored when the conversation is resumed.
"""

from __future__ import annotations

from typing import Final

SESSION_WORK_MODE_KEY: Final = "_tui_work_mode"
DEFAULT_WORK_MODE: Final = "everyday"

# ``None`` means "use the user's already-configured supplemental tools".  This
# intentionally remains an advanced escape hatch; the named modes above it are
# the lean, predictable choices exposed by the Desktop new-session selector.
WORK_MODE_TOOLSETS: Final[dict[str, tuple[str, ...] | None]] = {
    "everyday": ("core",),
    "search_read": ("core", "web", "vision"),
    "build_websites": ("coding", "browser_auth"),
    "automate": ("automation",),
    "robinhood_research": ("core", "robinhood_research"),
    "more": None,
}


def is_work_mode(value: object) -> bool:
    """Return whether *value* names a supported Desktop work mode."""
    return isinstance(value, str) and value in WORK_MODE_TOOLSETS


def selected_work_mode(value: object) -> str | None:
    """Return a valid persisted mode, or ``None`` for legacy/invalid values."""
    return str(value) if is_work_mode(value) else None


def toolsets_for_work_mode(value: object) -> tuple[str, ...] | None:
    """Return a named mode's toolsets, or ``None`` for configured/invalid modes."""
    mode = selected_work_mode(value)
    return WORK_MODE_TOOLSETS.get(mode) if mode else None


def validate_work_mode_readiness(value: object) -> None:
    """Fail before agent construction rather than freeze an unusable scope.

    Called after bounded startup discovery, including on cold resume. Never
    changes the integration config or launches an interactive OAuth flow.
    """
    if value != "robinhood_research":
        return
    from hermes_cli.config import load_config
    from model_tools import get_tool_definitions
    from toolsets import resolve_toolset
    from tools.mcp_tool import get_mcp_status

    server = (load_config().get("mcp_servers") or {}).get("robinhood")
    if not isinstance(server, dict) or not server.get("enabled", True):
        raise ValueError(
            "Robinhood Research requires the configured, enabled Robinhood MCP. "
            "Set it up in Tools before starting this session."
        )
    status = next((s for s in get_mcp_status() if s["name"] == "robinhood"), {})
    if not status.get("connected"):
        raise ValueError(
            "Robinhood Research: Robinhood MCP is disconnected or still discovering. "
            "Run `hermes mcp test robinhood` and retry after it connects. "
            "Authentication has not been diagnosed; no tools were enabled."
        )
    expected = set(resolve_toolset("robinhood_research"))
    available = {
        td["function"]["name"] for td in get_tool_definitions(
            enabled_toolsets=["robinhood_research"], quiet_mode=True,
            skip_tool_search_assembly=True,
        )
    }
    if expected - available:
        raise ValueError(
            "Robinhood Research is not ready: required market-data tools are "
            "unavailable (connection/discovery or configured tool filter). "
            "Run `hermes mcp test robinhood`; check its tool selection, then "
            "retry in a new Robinhood Research session. No tools were enabled."
        )
