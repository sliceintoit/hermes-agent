"""Real-path pre-import regressions; fake root ownership only in approval tests."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from hermes_cli import extension_gate as gate


def payload(tmp_path):
    directory = tmp_path / 'external'
    directory.mkdir()
    marker = tmp_path / 'executed'
    (directory / '__init__.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")\n')
    return directory, marker


def test_unapproved_tree_denied(tmp_path):
    directory, marker = payload(tmp_path)
    with pytest.raises(gate.ExtensionDenied):
        gate.require_directory(directory)
    assert not marker.exists()


def test_provider_does_not_execute(tmp_path):
    import providers
    directory, marker = payload(tmp_path)
    providers._import_plugin_dir(directory, 'user')
    assert not marker.exists()


def test_memory_and_context_do_not_execute(tmp_path):
    from plugins.memory import _load_provider_from_dir
    from plugins.context_engine import _load_engine_from_dir
    directory, marker = payload(tmp_path)
    assert _load_provider_from_dir(directory) is None
    assert _load_engine_from_dir(directory) is None
    assert not marker.exists()


def test_ordinary_plugin_source_label_cannot_bypass(tmp_path):
    from hermes_cli.plugins import PluginManager, PluginManifest
    directory, marker = payload(tmp_path)
    manifest = PluginManifest(path=str(directory), source='bundled', name='probe', key='probe')
    with pytest.raises(gate.ExtensionDenied):
        PluginManager()._load_directory_module(manifest)
    assert not marker.exists()


def test_entrypoint_denied_before_discovery(monkeypatch):
    import importlib.metadata
    from hermes_cli.plugins import PluginManager, PluginManifest
    discover = Mock()
    monkeypatch.setattr(importlib.metadata, 'entry_points', discover)
    with pytest.raises(gate.ExtensionDenied):
        PluginManager()._load_entrypoint_module(PluginManifest(name='probe'))
    discover.assert_not_called()


def test_mcp_denied_before_osv_or_spawn(monkeypatch):
    from tools import mcp_tool
    from tools import osv_check
    spawn = Mock()
    osv = Mock()
    monkeypatch.setattr(mcp_tool, 'stdio_client', spawn)
    monkeypatch.setattr(osv_check, 'check_package_for_malware', osv)
    with pytest.raises(gate.ExtensionDenied):
        asyncio.run(mcp_tool.MCPServerTask('probe')._run_stdio({'command':'npx'}))
    spawn.assert_not_called()
    osv.assert_not_called()


def test_mcp_denial_is_not_retried(monkeypatch):
    from tools.mcp_tool import MCPServerTask
    deny = Mock(side_effect=gate.ExtensionDenied('blocked'))
    monkeypatch.setattr(gate, 'deny_local_mcp', deny)
    server = MCPServerTask('probe')
    with pytest.raises(gate.ExtensionDenied):
        asyncio.run(server.start({'command':'npx'}))
    assert deny.call_count == 1


def test_approved_provider_imports(tmp_path, monkeypatch):
    import providers
    directory, marker = payload(tmp_path)
    policy = tmp_path / 'policy.json'
    monkeypatch.setattr(gate, 'POLICY_PATH', policy)
    monkeypatch.setattr(gate, '_immutable', lambda path: None)
    policy.write_text(json.dumps({'schema_version':1,'directories':[{'path':str(directory),'sha256':gate.tree_digest(directory)}]}))
    providers._import_plugin_dir(directory, 'user')
    assert marker.read_text() == 'bad'


def test_approved_digest_then_changed_content_denied(tmp_path, monkeypatch):
    directory, _ = payload(tmp_path)
    policy = tmp_path / 'policy.json'
    monkeypatch.setattr(gate, 'POLICY_PATH', policy)
    # Only simulate ownership, never bypass content comparison.
    monkeypatch.setattr(gate, '_immutable', lambda path: None)
    policy.write_text(json.dumps({'schema_version':1,'directories':[{'path':str(directory),'sha256':gate.tree_digest(directory)}]}))
    gate.require_directory(directory)
    (directory / 'dependency.py').write_text('changed')
    with pytest.raises(gate.ExtensionDenied):
        gate.require_directory(directory)


def test_malformed_and_missing_policy_fail_closed(tmp_path, monkeypatch):
    directory, _ = payload(tmp_path)
    policy = tmp_path / 'policy.json'
    monkeypatch.setattr(gate, 'POLICY_PATH', policy)
    monkeypatch.setattr(gate, '_immutable', lambda path: None)
    for value in ['not json','[]','{"schema_version":2}','{"schema_version":1,"directories":null}']:
        policy.write_text(value)
        with pytest.raises(gate.ExtensionDenied):
            gate.require_directory(directory)
    policy.unlink()
    with pytest.raises(gate.ExtensionDenied):
        gate.require_directory(directory)


def test_user_owned_policy_is_not_authority(tmp_path, monkeypatch):
    directory, _ = payload(tmp_path)
    policy = tmp_path / 'policy.json'
    policy.write_text('{"schema_version":1,"directories":[]}')
    monkeypatch.setattr(gate, 'POLICY_PATH', policy)
    with pytest.raises(gate.ExtensionDenied):
        gate.require_directory(directory)


def test_memory_cli_does_not_execute(tmp_path, monkeypatch):
    from plugins import memory
    directory, marker = payload(tmp_path)
    (directory / 'cli.py').write_text((directory / '__init__.py').read_text())
    monkeypatch.setattr(memory, '_get_active_memory_provider', lambda: 'probe')
    monkeypatch.setattr(memory, 'find_provider_dir', lambda name: directory)
    assert memory.discover_plugin_cli_commands() == []
    assert not marker.exists()


def test_bundled_baseline_allowed():
    gate.require_directory(gate.BUNDLED_ROOT / 'memory')


def test_symlink_into_bundle_not_baseline(tmp_path):
    alias = tmp_path / 'alias'
    alias.symlink_to(gate.BUNDLED_ROOT / 'memory', target_is_directory=True)
    with pytest.raises(gate.ExtensionDenied):
        gate.require_directory(alias)
