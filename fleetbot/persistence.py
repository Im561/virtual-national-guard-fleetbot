from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import Aircraft, FleetSnapshot


def snapshot_to_record(snapshot: FleetSnapshot) -> dict[str, Any]:
    return {
        "version": 1,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "aircraft": [asdict(item) for item in snapshot.aircraft],
    }


def snapshot_from_record(record: dict[str, Any]) -> FleetSnapshot:
    fetched_at = datetime.fromisoformat(str(record["fetched_at"]))
    aircraft_records = record.get("aircraft")
    if not isinstance(aircraft_records, list):
        raise ValueError("Persistent fleet cache has no aircraft list.")

    aircraft = tuple(
        Aircraft(**item)
        for item in aircraft_records
        if isinstance(item, dict)
    )
    return FleetSnapshot(
        aircraft=aircraft,
        fetched_at=fetched_at,
        source="disk",
        stale=True,
        last_error="Loaded from persistent cache; waiting for a live refresh.",
    )


def load_snapshot(path: str) -> FleetSnapshot | None:
    target = Path(path)
    if not target.is_file():
        return None
    record = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("Persistent fleet cache is not a JSON object.")
    return snapshot_from_record(record)


def save_snapshot(path: str, snapshot: FleetSnapshot) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(snapshot_to_record(snapshot), separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(target)
