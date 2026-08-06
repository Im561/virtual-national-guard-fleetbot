import asyncio
import json
import subprocess
from pathlib import Path

from app.live_delta import build_live_delta
from app.main import ConnectionManager


ROOT = Path(__file__).resolve().parents[1]


class FakeWebSocket:
    def __init__(self, delay: float = 0.0) -> None:
        self.accepted = False
        self.messages: list[str] = []
        self.delay = delay
        self.active_sends = 0
        self.max_active_sends = 0
        self.send_started = asyncio.Event()

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, value: str) -> None:
        self.active_sends += 1
        self.max_active_sends = max(self.max_active_sends, self.active_sends)
        self.send_started.set()
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.messages.append(value)
        finally:
            self.active_sends -= 1


def live_payload(revision: int, order: tuple[str, ...] = ("AAL1", "DAL2")) -> dict:
    return {
        "type": "live",
        "revision": revision,
        "feed_sequence": revision,
        "pilots": [{"callsign": callsign, "lat": 25.0 + index} for index, callsign in enumerate(order)],
        "alerts": [],
        "operations": [],
        "manual_intercepts": [],
        "intercept_controls": [],
        "temporary_exemptions": [],
        "controllers": [],
        "stats": {"monitored_aircraft": len(order)},
    }


def test_delta_includes_collection_order_when_server_order_changes() -> None:
    previous = live_payload(1, ("AAL1", "DAL2"))
    current = live_payload(2, ("DAL2", "AAL1"))
    delta = build_live_delta(previous, current)
    assert delta is not None
    assert delta["collections"]["pilots"]["order"] == ["DAL2", "AAL1"]


def test_browser_delta_client_applies_server_order() -> None:
    module_path = ROOT / "app/static/modules/delta-client.js"
    script = f"""
const fs = require('fs');
const vm = require('vm');
const context = {{ console }};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(module_path))}, 'utf8'), context);
const previous = {{type:'live', revision:1, pilots:[{{callsign:'AAL1'}},{{callsign:'DAL2'}}]}};
const delta = {{type:'delta', base_revision:1, revision:2, changes:{{}}, collections:{{pilots:{{upsert:[],remove:[],order:['DAL2','AAL1']}}}}}};
const result = context.VngDeltaClient.applyDelta(previous, delta);
process.stdout.write(JSON.stringify(result.pilots.map(item => item.callsign)));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == ["DAL2", "AAL1"]


def test_concurrent_live_broadcasts_are_serialized_and_revision_safe() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket(delay=0.05)
        manager.connections.add(socket)
        manager.client_ids[socket] = "console-a"

        first_task = asyncio.create_task(manager.broadcast(live_payload(1)))
        await socket.send_started.wait()
        second_task = asyncio.create_task(manager.broadcast(live_payload(2, ("AAL1", "UAL3"))))
        await asyncio.gather(first_task, second_task)

        messages = [json.loads(value) for value in socket.messages]
        assert messages[0]["type"] == "live" and messages[0]["revision"] == 1
        assert messages[1]["type"] == "delta"
        assert messages[1]["base_revision"] == 1 and messages[1]["revision"] == 2
        assert socket.max_active_sends == 1

    asyncio.run(scenario())


def test_new_console_receives_full_baseline_before_presence_and_deltas() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        existing = FakeWebSocket()
        manager.connections.add(existing)
        manager.client_ids[existing] = "existing"
        await manager.broadcast(live_payload(1))

        newcomer = FakeWebSocket()
        await manager.connect(newcomer, "new-console", live_payload(2, ("AAL1", "UAL3")))
        initial = [json.loads(value) for value in newcomer.messages]
        assert newcomer.accepted is True
        assert initial[0]["type"] == "live" and initial[0]["revision"] == 1
        assert initial[1] == {"type": "presence", "viewer_count": 2}

        await manager.broadcast(live_payload(2, ("AAL1", "UAL3")))
        update = json.loads(newcomer.messages[-1])
        assert update["type"] == "delta"
        assert update["base_revision"] == 1 and update["revision"] == 2

    asyncio.run(scenario())


def test_modal_focus_and_leaflet_integrity_hardening_are_present() -> None:
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "function trapModalFocus" in js
    assert "restoreStoredFocus('interceptPreviousFocus')" in js
    assert "setScrambleModalVisible(false)" in js
    assert "event.key === 'Enter' && !el('acknowledge-scramble').disabled" not in js
    assert 'integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="' in index
    assert 'integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="' in index
