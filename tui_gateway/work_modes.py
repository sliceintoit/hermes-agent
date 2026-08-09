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
