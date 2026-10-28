"""Stalled-peer isolation and frame serialization (upstream #106581)."""
import asyncio
import json

from tui_gateway import ws as ws_mod


def test_stalled_peer_closes_and_releases_replies_without_harming_healthy_peer(monkeypatch):
    monkeypatch.setattr(ws_mod, "_WS_SEND_DEADLINE_S", 0.05)

    async def run():
        class Socket:
            def __init__(self, stalled=False):
                self.stalled = stalled
                self.release = asyncio.Event()
                self.closed = []
                self.sent = []

            async def send_text(self, text):
                if self.stalled:
                    await self.release.wait()
                self.sent.append(json.loads(text))

            async def close(self, code=1000):
                self.closed.append(code)
                self.release.set()

        slow, fast = Socket(True), Socket()
        loop = asyncio.get_running_loop()
        blocked = ws_mod.WSTransport(slow, loop)
        healthy = ws_mod.WSTransport(fast, loop)
        first = asyncio.create_task(blocked.write_async({"id": 1}))
        await asyncio.sleep(0)
        second = asyncio.create_task(blocked.write_async({"id": 2}))
        assert await healthy.write_async({"id": "healthy"})
        assert await asyncio.wait_for(asyncio.gather(first, second), 1) == [False, False]
        for _ in range(10):
            if slow.closed:
                break
            await asyncio.sleep(0.01)
        assert slow.closed == [1011]
        assert fast.closed == []
        assert fast.sent == [{"id": "healthy"}]
        assert not blocked.write({"id": 3})

    asyncio.run(run())


def test_concurrent_sends_never_overlap_and_preserve_admission_order():
    async def run():
        class Socket:
            def __init__(self):
                self.active = False
                self.sent = []

            async def send_text(self, text):
                assert not self.active
                self.active = True
                await asyncio.sleep(0)
                self.sent.append(json.loads(text)["id"])
                self.active = False

        socket = Socket()
        transport = ws_mod.WSTransport(socket, asyncio.get_running_loop())
        assert all(await asyncio.gather(*(transport.write_async({"id": i}) for i in range(50))))
        assert socket.sent == list(range(50))

    asyncio.run(run())
