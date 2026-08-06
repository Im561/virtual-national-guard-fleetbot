from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class OperationalStateStore:
    """SQLite-backed storage for shared operator workflow state."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS operational_state ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        return connection

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM operational_state WHERE id = 1").fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def save(self, payload: dict[str, Any], updated_at: str) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO operational_state(id, payload, updated_at) VALUES(1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (encoded, updated_at),
            )
            connection.commit()
