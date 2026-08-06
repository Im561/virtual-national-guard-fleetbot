from __future__ import annotations

from typing import Any


def track_signature(track: dict[str, Any] | None) -> tuple[Any, ...]:
    track = track or {}
    return (
        str(track.get("callsign") or "").upper(),
        round(float(track.get("lat") or track.get("latitude") or 0.0), 5),
        round(float(track.get("lon") or track.get("longitude") or 0.0), 5),
        int(round(float(track.get("heading") or 0.0))) % 360,
        int(round(float(track.get("groundspeed") or 0.0))),
        int(round(float(track.get("altitude") or 0.0))),
    )


def intercept_pair_signature(interceptor: dict[str, Any], target: dict[str, Any]) -> tuple[Any, ...]:
    return track_signature(interceptor), track_signature(target)
