"""Cron profile discovery must not scan skills or block the chat event loop."""

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from websockets.sync.client import connect


@pytest.fixture()
def profile_homes(tmp_path, monkeypatch):
    from hermes_cli import profiles

    home = tmp_path / ".hermes"
    worker = home / "profiles" / "worker_alpha"
    for path in (home, worker):
        (path / "cron").mkdir(parents=True)
    monkeypatch.setattr(profiles, "_get_default_hermes_home", lambda: home)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: home / "profiles")
    return home, worker


def test_cron_discovery_never_counts_skills(profile_homes, monkeypatch):
    from hermes_cli import profiles, web_server

    scans = []

    def count_skills(home):
        scans.append(home)
        return 17

    monkeypatch.setattr(profiles, "_count_skills", count_skills)
    (profile_homes[0] / "profiles" / "default").mkdir()
    (profile_homes[0] / "profiles" / "invalid name").mkdir()
    (profile_homes[0] / "profiles" / "not_a_profile").touch()
    assert [p["name"] for p in web_server._cron_profile_dicts()] == ["default", "worker_alpha"]
    assert scans == [], "Cron needs profile names, not recursive skill counts"


@pytest.fixture()
def cron_server():
    """Serve the real cron routes and chat transport, without scheduler startup."""
    from hermes_cli import web_server
    from tui_gateway.ws import handle_ws

    app = FastAPI()
    app.router.routes.extend(
        route for route in web_server.app.routes
        if getattr(route, "path", "").startswith("/api/cron/jobs")
        or getattr(route, "path", "") == "/api/cron/blueprints/instantiate"
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.websocket("/api/ws")
    async def chat(ws: WebSocket):
        await handle_ws(ws)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            app, log_level="error", lifespan="off", loop="asyncio",
            ws="websockets", ws_ping_interval=None,
        ))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started, "Local test server failed to become ready"
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/cron/jobs", None),
    ("GET", "/api/cron/jobs?profile=default", None),
    ("GET", "/api/cron/jobs/{id}", None),
    ("GET", "/api/cron/jobs/{id}/runs", None),
    ("POST", "/api/cron/jobs", {"prompt": "test", "schedule": "every 1h"}),
    ("PUT", "/api/cron/jobs/{id}", {"updates": {"name": "renamed"}}),
    ("POST", "/api/cron/jobs/{id}/pause", None),
    ("POST", "/api/cron/jobs/{id}/resume", None),
    ("POST", "/api/cron/jobs/{id}/trigger", None),
    ("DELETE", "/api/cron/jobs/{id}", None),
    ("POST", "/api/cron/blueprints/instantiate", {
        "blueprint": "morning-brief", "values": {"deliver": "local"},
    }),
])
def test_slow_cron_profile_io_does_not_block_http_or_websocket(
    profile_homes, monkeypatch, cron_server, method, path, body,
):
    from hermes_cli import profiles, web_server

    job = web_server._call_cron_for_profile(
        "default", "create_job", prompt="test", schedule="every 1h",
    )
    assert isinstance(job, dict)
    entered = threading.Event()
    release = threading.Event()

    def slow_profile_home():
        entered.set()
        # Safety bound only: the test must finish HTTP and WS checks BEFORE
        # releasing this gate. It must not pass by waiting for the slow I/O.
        assert release.wait(5), "Slow profile lookup was not released"
        return profile_homes[0]

    monkeypatch.setattr(profiles, "_get_default_hermes_home", slow_profile_home)
    with httpx.Client(base_url=cron_server, timeout=10) as client:
        with connect(cron_server.replace("http:", "ws:") + "/api/ws") as ws:
            assert json.loads(ws.recv(timeout=2))["params"]["type"] == "gateway.ready"
            with ThreadPoolExecutor(max_workers=1) as pool:
                request = pool.submit(client.request, method, path.format(id=job["id"]), json=body)
                try:
                    assert entered.wait(2), "Cron request did not enter profile I/O"
                    assert client.get("/health", timeout=0.5).status_code == 200
                    assert ws.ping().wait(0.5), "WebSocket ping blocked behind cron I/O"
                    # Exercise real application-frame delivery too, not just TCP/control frames.
                    ws.send("{")
                    assert json.loads(ws.recv(timeout=0.5))["error"]["code"] == -32700
                    assert not request.done(), "Probe ran after the slow request completed"
                finally:
                    release.set()
                assert request.result(timeout=5).status_code == 200


def test_concurrent_cron_writes_keep_profiles_isolated(profile_homes, cron_server):
    from cron import jobs as cron_jobs

    original_paths = cron_jobs.CRON_DIR, cron_jobs.JOBS_FILE, cron_jobs.OUTPUT_DIR
    profiles = ["default", "worker_alpha"] * 5

    def create(profile):
        with httpx.Client(base_url=cron_server, timeout=5) as client:
            response = client.post("/api/cron/jobs", params={"profile": profile}, json={
                "prompt": f"For {profile}", "schedule": "every 1h",
            })
            assert response.status_code == 200
            assert response.json()["profile"] == profile

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(create, profiles))
    with httpx.Client(base_url=cron_server, timeout=5) as client:
        for profile in set(profiles):
            jobs = client.get("/api/cron/jobs", params={"profile": profile}).json()
            assert len(jobs) == 5
            assert all(job["profile"] == profile and job["prompt"] == f"For {profile}" for job in jobs)
    assert (cron_jobs.CRON_DIR, cron_jobs.JOBS_FILE, cron_jobs.OUTPUT_DIR) == original_paths
