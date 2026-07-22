"""Live, tail-able transcripts for delegated subagents.

Each delegate_task dispatch can create one append-only log per child under::

    <hermes_home>/cache/delegation/live/<delegation_id>/task-<n>.log

The transcript files are pre-created at dispatch time so ``tail -f`` can
attach immediately. Every line, header field, and manifest value is forced
through the canonical credential redactor. If redaction is unavailable, the
module withholds data rather than writing raw text.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

LIVE_RETENTION_DAYS = 7
_ASSISTANT_MAX = 600
_THINKING_MAX = 300
_ARGS_MAX = 220
_RESULT_MAX = 400
_KICKOFF_MAX = 500
_STREAM_BUFFER_FLUSH_CHARS = 4000
_WITHHELD = "[withheld: redaction unavailable]"


def live_transcript_root() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "cache" / "delegation" / "live"


def new_live_delegation_id() -> str:
    return f"deleg_{uuid.uuid4().hex[:8]}"


def _sanitize_line(text: Any) -> str:
    s = "" if text is None else str(text)
    s = " ".join(s.split())
    return s


def _secure_text(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    try:
        from agent.redact import redact_sensitive_text

        redacted = redact_sensitive_text(text, force=True)
        return redacted if redacted is not None else ""
    except Exception:
        return _WITHHELD


def _secure_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _secure_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_secure_value(v) for v in value]
    if isinstance(value, tuple):
        return [_secure_value(v) for v in value]
    if isinstance(value, Path):
        return _secure_text(str(value))
    if isinstance(value, str):
        return _secure_text(value)
    return value


def _json_manifest(data: Dict[str, Any]) -> str:
    return json.dumps(_secure_value(data), ensure_ascii=False, indent=2, sort_keys=True)


class LiveTranscriptWriter:
    """Append-only human-readable event log for one subagent task."""

    def __init__(
        self,
        delegation_id: str,
        task_index: int,
        goal: str,
        context: Optional[str] = None,
        root: Optional[Path] = None,
    ):
        self.delegation_id = delegation_id
        self.task_index = task_index
        self._ok = True
        self._lock = threading.Lock()
        self._stream_buf: List[str] = []
        self._stream_len = 0
        self._finalized = False
        try:
            base = root or live_transcript_root()
            d = base / delegation_id
            d.mkdir(parents=True, exist_ok=True)
            self.path = d / f"task-{task_index}.log"
            header = [
                "=== Hermes subagent live transcript ===",
                f"delegation: {_secure_text(delegation_id)}   task: {task_index}",
                f"goal: {_secure_text(_sanitize_line(goal)[:_KICKOFF_MAX])}",
                f"started: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "(append-only; streams while the subagent runs — tail -f me)",
                "=" * 40,
            ]
            self.path.write_text("\n".join(header) + "\n", encoding="utf-8")
            kickoff = "kickoff: " + _sanitize_line(goal)[:_KICKOFF_MAX]
            if context:
                kickoff += " | context: " + _sanitize_line(context)[:_KICKOFF_MAX]
            self.event("user", kickoff)
        except Exception as exc:
            logger.debug(
                "Live transcript init failed (%s task %s): %s",
                delegation_id,
                task_index,
                exc,
            )
            self._ok = False
            self.path = None

    def event(self, role: str, text: str) -> None:
        if not self._ok or getattr(self, "path", None) is None:
            return
        line = f"{time.strftime('%H:%M:%S')} {role:<9}| {_secure_text(_sanitize_line(text))}\n"
        try:
            with self._lock:
                path = self.path
                if path is None:
                    return
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception as exc:
            self._ok = False
            logger.debug("Live transcript write failed (%s): %s", self.path, exc)

    def assistant_text(self, text: str) -> None:
        t = _sanitize_line(text)[:_ASSISTANT_MAX]
        if t:
            self.event("assistant", t)

    def thinking(self, text: str) -> None:
        t = _sanitize_line(text)[:_THINKING_MAX]
        if t:
            self.event("think", t)

    def tool_start(self, name: str, args_preview: Any = None) -> None:
        self.flush_stream()
        args = _sanitize_line(args_preview)[:_ARGS_MAX]
        self.event("tool", f"-> {name or '?'}({args})")

    def tool_result(
        self,
        name: str,
        result: Any = None,
        duration: Any = None,
        is_error: bool = False,
    ) -> None:
        status = "ERROR" if is_error else "ok"
        dur = ""
        try:
            if duration is not None:
                dur = f" {float(duration):.1f}s"
        except (TypeError, ValueError):
            pass
        result_text = _sanitize_line(result)[:_RESULT_MAX]
        self.event("result", f"{name or '?'} {status}{dur}: {result_text}")

    def marker(self, text: str) -> None:
        self.flush_stream()
        self.event("final", _sanitize_line(text)[:_ASSISTANT_MAX])

    def add_stream_delta(self, delta: str) -> None:
        if not delta or not self._ok:
            return
        self._stream_buf.append(delta)
        self._stream_len += len(delta)
        if self._stream_len >= _STREAM_BUFFER_FLUSH_CHARS:
            self.flush_stream()

    def flush_stream(self) -> None:
        if not self._stream_buf:
            return
        text = "".join(self._stream_buf)
        self._stream_buf = []
        self._stream_len = 0
        self.assistant_text(text)

    def finalize(self, **kwargs: Any) -> None:
        if self._finalized:
            return
        self._finalized = True
        self.flush_stream()
        status = str(kwargs.get("status") or "unknown")
        duration = kwargs.get("duration_seconds")
        summary = kwargs.get("summary") or kwargs.get("result") or kwargs.get("error")
        exit_reason = kwargs.get("exit_reason")
        parts = [f"end status={status}"]
        if duration is not None:
            try:
                parts.append(f"duration={float(duration):.2f}s")
            except (TypeError, ValueError):
                pass
        if exit_reason:
            parts.append(f"exit_reason={exit_reason}")
            if exit_reason == "max_iterations":
                parts.append("iteration budget exhausted")
        if summary:
            parts.append(f"summary={_sanitize_line(summary)[:_ASSISTANT_MAX]}")
        self.event("final", " | ".join(parts))

    def observe(
        self,
        event_type: Any,
        tool_name: Any = None,
        preview: Any = None,
        args: Any = None,
        **kwargs: Any,
    ) -> None:
        et = str(event_type or "")
        if et in {"tool.started", "subagent.tool"}:
            self.tool_start(str(tool_name or ""), preview if preview is not None else args)
        elif et == "tool.completed":
            self.tool_result(
                str(tool_name or ""),
                result=kwargs.get("result"),
                duration=kwargs.get("duration"),
                is_error=bool(kwargs.get("is_error")),
            )
        elif et in {"_thinking", "reasoning.available", "subagent.thinking"}:
            self.thinking(str(tool_name or preview or ""))
        elif et == "subagent.text":
            self.add_stream_delta(str(preview or ""))
        elif et == "subagent.start":
            self.event("start", _sanitize_line(preview or "")[:_KICKOFF_MAX])
        elif et == "subagent.progress":
            text = _sanitize_line(preview or tool_name or "")[:_ASSISTANT_MAX]
            if text:
                self.event("progress", text)
        elif et == "subagent.complete":
            self.finalize(**kwargs)
        elif et == "subagent.spawn_requested":
            self.event("spawn", _sanitize_line(preview or tool_name or "")[:_KICKOFF_MAX])


def create_live_transcripts(
    tasks: List[Dict[str, Any]],
    *,
    context: Optional[str] = None,
    root: Optional[Path] = None,
) -> tuple[Optional[str], List[Optional[LiveTranscriptWriter]], List[str]]:
    """Pre-create one transcript file per task and write an initial manifest."""
    try:
        prune_stale_live_dirs(root=root)
        delegation_id = new_live_delegation_id()
        base = root or live_transcript_root()
        delegation_dir = base / delegation_id
        delegation_dir.mkdir(parents=True, exist_ok=True)

        writers: List[Optional[LiveTranscriptWriter]] = []
        paths: List[str] = []
        manifest_tasks: List[Dict[str, Any]] = []
        created_at = time.time()

        for index, task in enumerate(tasks):
            task_goal = task.get("goal", "") if isinstance(task, dict) else ""
            task_context = task.get("context") if isinstance(task, dict) else None
            writer = LiveTranscriptWriter(
                delegation_id,
                index,
                task_goal,
                context=task_context if task_context is not None else context,
                root=base,
            )
            if not getattr(writer, "path", None):
                raise RuntimeError("failed to pre-create transcript file")
            writers.append(writer)
            paths.append(str(writer.path))
            manifest_tasks.append(
                {
                    "task_index": index,
                    "goal": task_goal,
                    "context": task_context if task_context is not None else context,
                    "toolsets": task.get("toolsets") if isinstance(task, dict) else None,
                    "role": task.get("role") if isinstance(task, dict) else None,
                    "model": task.get("model") if isinstance(task, dict) else None,
                    "status": "running",
                    "log": str(writer.path),
                }
            )

        manifest = {
            "delegation_id": delegation_id,
            "created_at": created_at,
            "created_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at)),
            "status": "running",
            "task_count": len(tasks),
            "context": context,
            "tasks": manifest_tasks,
        }
        (delegation_dir / "manifest.json").write_text(
            _json_manifest(manifest), encoding="utf-8"
        )
        return delegation_id, writers, paths
    except Exception as exc:
        logger.debug("create_live_transcripts failed: %s", exc)
        return None, [None] * len(tasks), []


def update_manifest_statuses(
    delegation_id: Optional[str],
    results: Iterable[Dict[str, Any]],
    *,
    root: Optional[Path] = None,
) -> None:
    if not delegation_id:
        return
    try:
        base = root or live_transcript_root()
        manifest_path = base / delegation_id / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tasks = manifest.get("tasks")
        if not isinstance(tasks, list):
            return
        by_index = {int(r.get("task_index", -1)): r for r in results if isinstance(r, dict)}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            idx = int(task.get("task_index", -1))
            result = by_index.get(idx)
            if not result:
                continue
            for key in ("status", "exit_reason", "summary", "error", "duration_seconds"):
                if key in result:
                    task[key] = _secure_value(result.get(key))
        if any(isinstance(task, dict) and task.get("status") == "running" for task in tasks):
            manifest["status"] = "running"
        else:
            manifest["status"] = "completed"
        manifest["completed_at"] = time.time()
        manifest_path.write_text(_json_manifest(manifest), encoding="utf-8")
    except Exception as exc:
        logger.debug("update_manifest_statuses failed (%s): %s", delegation_id, exc)


def prune_stale_live_dirs(
    *,
    max_age_days: int = LIVE_RETENTION_DAYS,
    root: Optional[Path] = None,
) -> int:
    try:
        base = root or live_transcript_root()
        if not base.exists():
            return 0
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0
        for child in base.iterdir():
            if not child.is_dir():
                continue
            if child.stat().st_mtime >= cutoff:
                continue
            try:
                shutil.rmtree(child)
                removed += 1
            except Exception as exc:
                logger.debug("Failed to prune live transcript dir %s: %s", child, exc)
        return removed
    except Exception as exc:
        logger.debug("prune_stale_live_dirs failed: %s", exc)
        return 0


def wrap_progress_callback(inner, writer: Optional[LiveTranscriptWriter]):
    """Tee a child's progress callback into the live transcript writer."""

    def _callback(event_type, tool_name=None, preview=None, args=None, **kwargs):
        if writer is not None:
            try:
                writer.observe(event_type, tool_name, preview, args, **kwargs)
            except Exception as exc:
                logger.debug("Live transcript observe failed: %s", exc)
        if inner is not None:
            try:
                inner(event_type, tool_name, preview, args, **kwargs)
            except Exception as exc:
                logger.debug("Inner progress callback failed: %s", exc)

    def _flush():
        if writer is not None:
            try:
                writer.flush_stream()
            except Exception as exc:
                logger.debug("Live transcript flush failed: %s", exc)
        if inner is not None and hasattr(inner, "_flush"):
            try:
                inner._flush()
            except Exception as exc:
                logger.debug("Inner progress callback flush failed: %s", exc)

    _callback._flush = _flush  # type: ignore[attr-defined]
    return _callback
