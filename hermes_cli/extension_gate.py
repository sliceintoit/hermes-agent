"""Pre-import extension policy. Not an OS sandbox or a terminal policy.

External code is denied unless a root-controlled immutable tree is approved.
No config/env/YOLO override. Pip entry points and local MCP are not approvable
in v1: their complete executable dependency closures are not established.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
import stat

POLICY_PATH = Path('/private/etc/hermes/extension-trust.json' if sys.platform == 'darwin'
                   else '/etc/hermes/extension-trust.json')
BUNDLED_ROOT = Path(__file__).resolve().parent.parent / 'plugins'


class ExtensionDenied(PermissionError):
    pass


def _immutable(path: Path) -> None:
    """Require real, root-owned, non-group/world-writable paths to filesystem root."""
    path = path.absolute()
    for item in (path, *path.parents):
        s = item.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise ExtensionDenied('Extension approval requires root-owned immutable paths')


def tree_digest(path: Path) -> str:
    """Hash every regular tree file; reject links, writable trees and special files."""
    _immutable(path)
    if not path.is_dir():
        raise ExtensionDenied('Extension must be a directory')
    h = hashlib.sha256()
    for item in sorted(path.rglob('*')):
        _immutable(item)
        s = item.lstat()
        if stat.S_ISDIR(s.st_mode):
            continue
        if not stat.S_ISREG(s.st_mode):
            raise ExtensionDenied('Special files are not approved extension content')
        relative = item.relative_to(path).as_posix().encode()
        data = item.read_bytes()
        h.update(len(relative).to_bytes(8, 'big') + relative)
        h.update(len(data).to_bytes(8, 'big') + data)
    return h.hexdigest()


def require_directory(path: Path) -> None:
    """Check before importing, even when a module is cached or manifest says bundled."""
    path = Path(path).absolute()
    # Only actual repo-bundled locations are baseline, never source labels.
    try:
        path.relative_to(BUNDLED_ROOT)
        if path.resolve().is_relative_to(BUNDLED_ROOT.resolve()):
            # A symlinked extension must not inherit bundled trust.
            if not any(p.is_symlink() for p in (path, *path.parents)):
                return
    except ValueError:
        pass
    try:
        _immutable(POLICY_PATH)
        policy = json.loads(POLICY_PATH.read_text())
        if policy.get('schema_version') != 1:
            raise ExtensionDenied('Unsupported extension policy')
        digest = tree_digest(path)
        if any(e.get('path') == str(path) and e.get('sha256') == digest
               for e in policy.get('directories', []) if isinstance(e, dict)):
            return
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ExtensionDenied('BLOCKED: external extension has no valid owner approval') from exc
    raise ExtensionDenied('BLOCKED: external extension is unapproved or changed')


def deny_entrypoint() -> None:
    raise ExtensionDenied('BLOCKED: external pip plugin entry points are unsupported by extension policy v1')


def deny_local_mcp() -> None:
    raise ExtensionDenied('BLOCKED: local MCP execution is unsupported by extension policy v1; remote MCP is unaffected')
