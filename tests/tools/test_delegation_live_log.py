"""Regression tests for live subagent transcript logging."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from queue import Empty
from unittest.mock import MagicMock

import pytest

from agent import redact as redact_mod
from tools import delegation_live_log as dll
from tools.process_registry import process_registry


TOKEN = "sk_test_1234567890abcdef1234"


@pytest.fixture(autouse=True)
def _reset_redaction_state():
    # The live transcript module imports the canonical redactor lazily, so the
    # tests can safely toggle its module-global state.
    yield


def _hermes_home(tmp_path: Path) -> Path:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir(parents=True, exist_ok=True)
    return hermes_home


def _read_tree(root: Path) -> str:
    parts = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_create_live_transcripts_precreates_logs_and_manifest(tmp_path, monkeypatch):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    tasks = [{"goal": f"build {TOKEN}", "context": f"ctx {TOKEN}"}]
    delegation_id, writers, paths = dll.create_live_transcripts(tasks, context=f"shared {TOKEN}")

    assert delegation_id and delegation_id.startswith("deleg_")
    assert len(writers) == 1 and writers[0] is not None
    assert len(paths) == 1

    log_path = Path(paths[0])
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8")
    assert TOKEN not in log_path.read_text(encoding="utf-8")

    manifest_path = hermes_home / "cache" / "delegation" / "live" / delegation_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["task_count"] == 1
    assert manifest["tasks"][0]["status"] == "running"
    assert TOKEN not in manifest_path.read_text(encoding="utf-8")


def test_live_transcript_writer_tees_progress_and_flushes(tmp_path, monkeypatch):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    _delegation_id, writers, _paths = dll.create_live_transcripts([
        {"goal": f"solve {TOKEN}"}
    ])
    writer = writers[0]
    assert writer is not None

    cb = dll.wrap_progress_callback(None, writer)
    cb("subagent.start", preview=f"starting {TOKEN}")
    cb("subagent.text", preview=f"streamed {TOKEN}")
    cb("subagent.complete", status="completed", summary=f"done {TOKEN}")
    cb_flush = getattr(cb, "_flush", None)
    if cb_flush is not None:
        cb_flush()

    assert writer.path is not None
    text = writer.path.read_text(encoding="utf-8")
    assert "starting" in text
    assert "streamed" in text
    assert "end status=completed" in text
    assert TOKEN not in text


def test_forced_redaction_survives_disabled_global_redaction(tmp_path, monkeypatch):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(redact_mod, "_REDACT_ENABLED", False)

    _delegation_id, writers, _paths = dll.create_live_transcripts([
        {"goal": f"inspect {TOKEN}", "context": f"ctx {TOKEN}"}
    ])
    writer = writers[0]
    assert writer is not None
    writer.finalize(status="completed", summary=f"summary {TOKEN}")

    assert writer.path is not None
    text = writer.path.read_text(encoding="utf-8")
    assert TOKEN not in text
    assert "summary" in text


def test_withholds_data_if_redactor_raises(tmp_path, monkeypatch):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(redact_mod, "redact_sensitive_text", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))

    _delegation_id, writers, _paths = dll.create_live_transcripts([
        {"goal": f"raw {TOKEN}", "context": f"ctx {TOKEN}"}
    ])
    writer = writers[0]
    assert writer is not None
    writer.finalize(status="completed", summary=f"done {TOKEN}")

    tree = _read_tree(hermes_home / "cache" / "delegation" / "live")
    assert TOKEN not in tree
    assert "[withheld: redaction unavailable]" in tree


@pytest.fixture
def delegate_parent():
    parent = MagicMock()
    parent._delegate_depth = 0
    parent.session_id = "sess-live"
    parent._interrupt_requested = False
    parent._active_children = []
    parent._active_children_lock = None
    return parent


_CREDS = {
    "model": "m",
    "provider": None,
    "base_url": None,
    "api_key": None,
    "api_mode": None,
    "command": None,
    "args": None,
}


def test_delegate_task_sync_result_includes_live_transcripts(tmp_path, monkeypatch, delegate_parent):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    import tools.delegate_tool as dt

    fake_child = MagicMock()
    fake_child._delegate_role = "leaf"
    fake_child.tool_progress_callback = None

    def make_child(**_kw):
        return fake_child

    def fake_run(task_index, goal, child=None, parent_agent=None, **_kw):
        cb = child.tool_progress_callback
        assert cb is not None
        cb("subagent.start", preview=goal)
        cb("subagent.text", preview=f"doing {TOKEN}")
        cb(
            "subagent.complete",
            status="completed",
            duration_seconds=0.1,
            summary=f"done {TOKEN}",
        )
        return {
            "task_index": task_index,
            "status": "completed",
            "summary": f"done {TOKEN}",
            "api_calls": 1,
            "duration_seconds": 0.1,
            "model": "m",
            "exit_reason": "completed",
        }

    monkeypatch.setattr(dt, "_build_child_agent", make_child)
    monkeypatch.setattr(dt, "_run_single_child", fake_run)
    monkeypatch.setattr(dt, "_resolve_delegation_credentials", lambda *a, **k: _CREDS)

    out = json.loads(dt.delegate_task(goal=f"sync goal {TOKEN}", parent_agent=delegate_parent))
    assert out["live_transcripts"]
    live = Path(out["live_transcripts"][0])
    assert live.exists()
    assert TOKEN not in live.read_text(encoding="utf-8")
    assert out["results"][0]["live_transcript"] == str(live)
    assert (hermes_home / "cache" / "delegation" / "live" / out["delegation_id"] / "manifest.json").exists()


def test_delegate_task_background_dispatch_includes_live_transcripts(tmp_path, monkeypatch, delegate_parent):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    import tools.delegate_tool as dt

    fake_child = MagicMock()
    fake_child._delegate_role = "leaf"
    fake_child._subagent_id = "s1"
    fake_child.tool_progress_callback = None

    gate = threading.Event()

    def make_child(**_kw):
        return fake_child

    def slow_run(task_index, goal, child=None, parent_agent=None, **_kw):
        gate.wait(timeout=10)
        return {
            "task_index": task_index,
            "status": "completed",
            "summary": f"done {TOKEN}",
            "api_calls": 1,
            "duration_seconds": 0.1,
            "model": "m",
            "exit_reason": "completed",
        }

    monkeypatch.setattr(dt, "_build_child_agent", make_child)
    monkeypatch.setattr(dt, "_run_single_child", slow_run)
    monkeypatch.setattr(dt, "_resolve_delegation_credentials", lambda *a, **k: _CREDS)

    out = json.loads(dt.delegate_task(goal=f"bg goal {TOKEN}", background=True, parent_agent=delegate_parent))
    assert out["status"] == "dispatched"
    assert out["live_transcripts"]
    live = Path(out["live_transcripts"][0])
    assert live.exists()
    assert TOKEN not in live.read_text(encoding="utf-8")

    gate.set()
    evt = None
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            evt = process_registry.completion_queue.get(timeout=0.25)
            break
        except Empty:
            continue
    assert evt is not None
    assert evt["live_transcripts"] == out["live_transcripts"]
    assert evt["results"][0]["live_transcript"] == out["live_transcripts"][0]

    # Prevent cross-test leakage if the background worker produced extra events.
    while True:
        try:
            process_registry.completion_queue.get_nowait()
        except Empty:
            break


def test_completion_formatter_mentions_live_transcripts(tmp_path, monkeypatch):
    hermes_home = _hermes_home(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    from tools.process_registry import _format_async_delegation

    live_path = str(hermes_home / "cache" / "delegation" / "live" / "deleg_1234" / "task-0.log")
    text = _format_async_delegation(
        {
            "delegation_id": "deleg_1234",
            "goal": "goal",
            "context": "ctx",
            "toolsets": ["default"],
            "role": "leaf",
            "model": "m",
            "status": "completed",
            "summary": "done",
            "api_calls": 1,
            "duration_seconds": 1.2,
            "dispatched_at": time.time() - 1,
            "completed_at": time.time(),
            "live_transcripts": [live_path],
        }
    )
    assert live_path in text
    assert "ASYNC DELEGATION COMPLETE" in text
