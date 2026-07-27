"""Routing metadata carried by async delegation completions."""

import time

import pytest

from tools import async_delegation as ad
from tools.process_registry import process_registry


@pytest.fixture(autouse=True)
def _clean_async_state():
    ad._reset_for_tests()
    while not process_registry.completion_queue.empty():
        process_registry.completion_queue.get_nowait()
    yield
    ad._reset_for_tests()
    while not process_registry.completion_queue.empty():
        process_registry.completion_queue.get_nowait()


def _drain_one(timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_registry.completion_queue.empty():
            return process_registry.completion_queue.get_nowait()
        time.sleep(0.01)
    raise AssertionError("completion event did not arrive")


def _assert_route(evt):
    assert evt["session_key"] == "durable-parent"
    assert evt["parent_session_id"] == "durable-parent"
    assert evt["origin_ui_session_id"] == "desktop-tab-7"
    assert evt["origin_profile"] == "highbeam"
    assert evt["origin_hermes_home"] == "/tmp/profiles/highbeam"


def test_single_completion_carries_exact_desktop_route():
    result = ad.dispatch_async_delegation(
        goal="route me",
        context=None,
        toolsets=None,
        role="leaf",
        model="m",
        session_key="durable-parent",
        parent_session_id="durable-parent",
        origin_ui_session_id="desktop-tab-7",
        origin_profile="highbeam",
        origin_hermes_home="/tmp/profiles/highbeam",
        runner=lambda: {"status": "completed", "summary": "done"},
    )
    assert result["status"] == "dispatched"
    _assert_route(_drain_one())


def test_batch_completion_carries_exact_desktop_route():
    result = ad.dispatch_async_delegation_batch(
        goals=["route us"],
        context=None,
        toolsets=None,
        role="leaf",
        model="m",
        session_key="durable-parent",
        parent_session_id="durable-parent",
        origin_ui_session_id="desktop-tab-7",
        origin_profile="highbeam",
        origin_hermes_home="/tmp/profiles/highbeam",
        runner=lambda: {"results": [{"status": "completed", "summary": "done"}]},
    )
    assert result["status"] == "dispatched"
    _assert_route(_drain_one())
