import asyncio
import json
from pathlib import Path

from app.main import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, value: str) -> None:
        self.messages.append(value)


def test_viewer_count_deduplicates_tabs_and_updates_presence():
    async def scenario() -> None:
        manager = ConnectionManager()
        first_tab = FakeWebSocket()
        second_tab = FakeWebSocket()
        other_console = FakeWebSocket()

        await manager.connect(first_tab, "console-a")
        assert manager.viewer_count == 1
        assert json.loads(first_tab.messages[-1]) == {"type": "presence", "viewer_count": 1}

        await manager.connect(second_tab, "console-a")
        assert manager.viewer_count == 1
        assert json.loads(second_tab.messages[-1])["viewer_count"] == 1

        await manager.connect(other_console, "console-b")
        assert manager.viewer_count == 2
        assert json.loads(first_tab.messages[-1])["viewer_count"] == 2
        assert json.loads(other_console.messages[-1])["viewer_count"] == 2

        await manager.disconnect(first_tab)
        assert manager.viewer_count == 2

        await manager.disconnect(second_tab)
        assert manager.viewer_count == 1
        assert json.loads(other_console.messages[-1]) == {"type": "presence", "viewer_count": 1}

        await manager.disconnect(other_console)
        assert manager.viewer_count == 0

    asyncio.run(scenario())


def test_viewer_counter_is_wired_through_server_and_footer():
    root = Path(__file__).parents[1]
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert '@app.get("/api/presence")' in main
    assert 'websocket.query_params.get("client_id")' in main
    assert '"viewer_count": manager.viewer_count' in main
    assert 'id="viewer-count"' in index
    assert 'class="footer-viewers"' in index
    assert "applySocketMessage" in js
    assert "data?.type === 'presence'" in js
    assert "/ws?client_id=${clientId}" in js
    assert ".footer-viewers" in css
    assert ".viewer-live-dot" in css
