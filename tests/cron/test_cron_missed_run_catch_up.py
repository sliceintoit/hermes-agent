"""Regression tests for opt-in recurring cron missed-run catch-up."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def cron_jobs(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    import hermes_constants
    import cron.jobs

    importlib.reload(hermes_constants)
    importlib.reload(cron.jobs)
    return cron.jobs


def _set_stale_next_run(cron_jobs, job_id: str, *, days_ago: int = 2) -> None:
    jobs = cron_jobs.load_jobs()
    jobs[0]["next_run_at"] = (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).isoformat()
    assert jobs[0]["id"] == job_id
    cron_jobs.save_jobs(jobs)


def test_stale_recurring_job_still_fast_forwards_by_default(cron_jobs):
    job = cron_jobs.create_job(prompt="daily", schedule="15 3 * * *")
    _set_stale_next_run(cron_jobs, job["id"])

    assert cron_jobs.get_due_jobs() == []
    stored = cron_jobs.get_job(job["id"])
    assert datetime.fromisoformat(stored["next_run_at"]) > cron_jobs._hermes_now()


def test_catch_up_job_runs_once_after_gateway_was_offline(cron_jobs):
    job = cron_jobs.create_job(
        prompt="daily",
        schedule="15 3 * * *",
        catch_up=True,
    )
    _set_stale_next_run(cron_jobs, job["id"])

    due = cron_jobs.get_due_jobs()

    assert [item["id"] for item in due] == [job["id"]]
    assert due[0]["catch_up"] is True


def test_catch_up_does_not_replay_every_missed_occurrence(cron_jobs):
    job = cron_jobs.create_job(
        prompt="frequent",
        schedule="every 5m",
        catch_up=True,
    )
    _set_stale_next_run(cron_jobs, job["id"], days_ago=7)

    due = cron_jobs.get_due_jobs()
    assert [item["id"] for item in due] == [job["id"]]

    assert cron_jobs.advance_next_run(job["id"]) is True
    assert cron_jobs.get_due_jobs() == []
    stored = cron_jobs.get_job(job["id"])
    assert datetime.fromisoformat(stored["next_run_at"]) > cron_jobs._hermes_now()
