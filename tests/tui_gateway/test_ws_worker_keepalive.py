"""A reconnect must not reap an idle orchestrator's notifying worker."""
from types import SimpleNamespace

import pytest

from tui_gateway import server
from tools.process_registry import process_registry


@pytest.mark.parametrize('notify,watch', [(True, []), (False, ['ready'])])
def test_detached_notifying_worker_is_kept_until_exit(monkeypatch, notify, watch):
    proc = SimpleNamespace(session_key='owner', exited=False,
                           notify_on_complete=notify, watch_patterns=watch)
    monkeypatch.setattr(process_registry, 'list_sessions', lambda: [{'session_id': 'worker'}])
    monkeypatch.setattr(process_registry, 'get', lambda _: proc)
    session = {'session_key': 'owner', 'transport': server._detached_ws_transport, 'running': False}
    assert not server._ws_session_is_orphaned(session)
    proc.exited = True
    assert server._ws_session_is_orphaned(session)


def test_unrelated_or_non_notifying_worker_does_not_pin_detached_session(monkeypatch):
    proc = SimpleNamespace(session_key='other', exited=False,
                           notify_on_complete=True, watch_patterns=[])
    monkeypatch.setattr(process_registry, 'list_sessions', lambda: [{'session_id': 'worker'}])
    monkeypatch.setattr(process_registry, 'get', lambda _: proc)
    session = {'session_key': 'owner', 'transport': server._detached_ws_transport}
    assert server._ws_session_is_orphaned(session)
    proc.session_key = 'owner'
    proc.notify_on_complete = False
    assert server._ws_session_is_orphaned(session)
