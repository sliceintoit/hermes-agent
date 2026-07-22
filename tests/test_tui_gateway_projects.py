"""Tests for the Projects backport wiring in the TUI/desktop gateway.

Covers the semantic port of upstream 4e023f5bc990 (GUI-only `project`
toolset enabling + project workspace-move callback) and the project
identity threading of 66a7825ebb0e, reduced to this branch's scope: no
Projects sidebar / project-tree RPCs.
"""

from __future__ import annotations

import contextlib

import pytest

import tui_gateway.server as server


# ---------------------------------------------------------------------------
# _load_enabled_toolsets: the `project` toolset is GUI-only, folded in by the
# gateway resolver (it is deliberately absent from _HERMES_CORE_TOOLS).
# ---------------------------------------------------------------------------


def test_toolsets_fold_project_on_coding_posture(monkeypatch):
    from agent import coding_context

    monkeypatch.delenv("HERMES_TUI_TOOLSETS", raising=False)
    monkeypatch.setattr(coding_context, "coding_selection", lambda **kw: ["terminal", "file"])

    enabled = server._load_enabled_toolsets()

    assert enabled is not None
    assert "project" in enabled
    assert "terminal" in enabled


def test_toolsets_fold_project_on_fallback_path(monkeypatch):
    from agent import coding_context
    from hermes_cli import tools_config

    monkeypatch.delenv("HERMES_TUI_TOOLSETS", raising=False)
    monkeypatch.setattr(coding_context, "coding_selection", lambda **kw: None)
    monkeypatch.setattr(
        tools_config,
        "_get_platform_tools",
        lambda cfg, platform, include_default_mcp_servers=True: {"terminal"},
    )

    enabled = server._load_enabled_toolsets()

    assert enabled is not None
    assert "project" in enabled


def test_toolsets_explicit_pin_unchanged(monkeypatch):
    # An explicit HERMES_TUI_TOOLSETS pin is the user's choice — the gateway
    # must not silently widen it.
    monkeypatch.setenv("HERMES_TUI_TOOLSETS", "terminal")

    enabled = server._load_enabled_toolsets()

    assert enabled == ["terminal"]


# ---------------------------------------------------------------------------
# _apply_project_workspace: explicit project_* tool calls re-anchor the live
# session's cwd and push session.info; nothing else moves cwd automatically.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_session(monkeypatch, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    session = {
        "session_key": "sess-key-1",
        "cwd": str(old),
        "running": False,
        "agent": None,
    }
    monkeypatch.setattr(server, "_sessions", {"sid-1": session})
    # Keep the real profile state.db out of the test.
    monkeypatch.setattr(
        server,
        "_session_db",
        lambda s: contextlib.contextmanager(lambda: (yield None))(),
    )
    return session, old, new


def test_apply_project_workspace_moves_cwd_and_emits(monkeypatch, fake_session):
    session, _old, new = fake_session
    emitted = []
    monkeypatch.setattr(server, "_emit", lambda *a: emitted.append(a))

    server._apply_project_workspace("sess-key-1", str(new), "Proj")

    assert session["cwd"] == str(new)
    assert session["explicit_cwd"] is True
    assert emitted and emitted[0][0] == "session.info"
    assert emitted[0][1] == "sid-1"
    assert emitted[0][2]["cwd"] == str(new)


def test_apply_project_workspace_resolves_session_by_key(monkeypatch, fake_session):
    # The tool's task_id is the durable session_key; _sessions is keyed by the
    # short runtime sid.
    session, _old, new = fake_session
    monkeypatch.setattr(server, "_emit", lambda *a: None)

    server._apply_project_workspace("sess-key-1", str(new))

    assert session["cwd"] == str(new)


def test_apply_project_workspace_rejects_missing_dir(monkeypatch, fake_session, tmp_path):
    session, old, _new = fake_session
    emitted = []
    monkeypatch.setattr(server, "_emit", lambda *a: emitted.append(a))

    server._apply_project_workspace("sess-key-1", str(tmp_path / "nope"))

    assert session["cwd"] == str(old)
    assert emitted == []


def test_apply_project_workspace_ignores_unknown_session(monkeypatch, fake_session):
    monkeypatch.setattr(server, "_emit", lambda *a: None)
    # Must not raise even when no session matches.
    server._apply_project_workspace("no-such-key", "/tmp")


def test_wire_callbacks_sets_project_workspace_callback():
    import tools.project_tools as project_tools

    server._wire_callbacks("sid-x")

    assert project_tools._workspace_callback is server._apply_project_workspace


# ---------------------------------------------------------------------------
# Active-project identity in status surfaces (reduced port of 66a7825ebb0e):
# _project_info_for_cwd reads the per-profile projects.db and is threaded
# through session.info and /status. Tests run under the suite-wide isolated
# HERMES_HOME (tests/conftest.py), so projects_db writes stay per-test.
# ---------------------------------------------------------------------------


@pytest.fixture
def named_project(tmp_path):
    from hermes_cli import projects_db as pdb

    folder = tmp_path / "repo"
    folder.mkdir()
    with pdb.connect_closing() as conn:
        pid = pdb.create_project(conn, name="Demo Project", folders=[str(folder)])
    return pid, folder


def test_project_info_for_cwd_resolves_named_project(named_project):
    pid, folder = named_project

    info = server._project_info_for_cwd(str(folder))

    assert info is not None
    assert info["id"] == pid
    assert info["name"] == "Demo Project"
    assert info["primary_path"] == str(folder)


def test_project_info_for_cwd_matches_nested_paths(named_project):
    _pid, folder = named_project
    nested = folder / "src" / "pkg"
    nested.mkdir(parents=True)

    info = server._project_info_for_cwd(str(nested))
    assert info is not None
    assert info["name"] == "Demo Project"


def test_project_info_for_cwd_none_outside_projects(tmp_path):
    assert server._project_info_for_cwd(str(tmp_path)) is None
    assert server._project_info_for_cwd("") is None


def test_session_info_threads_project(monkeypatch, named_project):
    from types import SimpleNamespace

    _pid, folder = named_project
    monkeypatch.setattr(server, "_load_cfg", lambda: {})
    monkeypatch.setattr(server, "_get_usage", lambda agent: {})
    monkeypatch.setattr(server, "_probe_credentials", lambda agent: None)
    agent = SimpleNamespace(
        model="test-model",
        provider="test-provider",
        reasoning_config=None,
        service_tier=None,
        tools=[],
    )
    session = {"session_key": "k1", "cwd": str(folder), "running": False}

    info = server._session_info(agent, session)

    assert info["project"]["name"] == "Demo Project"


def test_session_info_project_none_without_match(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(server, "_load_cfg", lambda: {})
    monkeypatch.setattr(server, "_get_usage", lambda agent: {})
    monkeypatch.setattr(server, "_probe_credentials", lambda agent: None)
    agent = SimpleNamespace(
        model="m", provider="p", reasoning_config=None, service_tier=None, tools=[]
    )

    info = server._session_info(agent, {"cwd": str(tmp_path), "running": False})

    assert info["project"] is None


def test_status_output_includes_project_line(monkeypatch, named_project):
    _pid, folder = named_project
    session = {"session_key": "k-status", "cwd": str(folder), "running": False, "agent": None}
    monkeypatch.setattr(server, "_sessions", {"sid-status": session})

    resp = server._methods["session.status"](1, {"session_id": "sid-status"})

    assert "error" not in resp, resp.get("error")
    assert "Project: Demo Project" in resp["result"]["output"]


def test_status_output_omits_project_line_without_match(monkeypatch, tmp_path):
    session = {"session_key": "k-plain", "cwd": str(tmp_path), "running": False, "agent": None}
    monkeypatch.setattr(server, "_sessions", {"sid-plain": session})

    resp = server._methods["session.status"](1, {"session_id": "sid-plain"})

    assert "error" not in resp, resp.get("error")
    assert "Project:" not in resp["result"]["output"]
