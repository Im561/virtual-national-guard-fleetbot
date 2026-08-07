from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence


class PhpVmsApiError(RuntimeError):
    """A safe, user-displayable phpVMS error."""


@dataclass(frozen=True, slots=True)
class Aircraft:
    id: str
    registration: str
    tail_number: str
    name: str
    icao: str
    type_name: str
    airport_id: str
    active: bool
    wing_id: str
    wing_name: str
    wing_code: str
    updated_at: str

    @property
    def display_tail(self) -> str:
        if self.tail_number and self.registration:
            if self.tail_number.casefold() != self.registration.casefold():
                return f"{self.registration} / {self.tail_number}"
        return self.registration or self.tail_number or self.name or self.id

    @property
    def display_type(self) -> str:
        return self.icao or self.type_name or "Unknown"


@dataclass(frozen=True, slots=True)
class FleetSnapshot:
    aircraft: tuple[Aircraft, ...]
    fetched_at: datetime
    source: str = "live"
    stale: bool = False
    last_error: str | None = None

    @property
    def age_seconds(self) -> int:
        age = datetime.now(timezone.utc) - self.fetched_at
        return max(0, int(age.total_seconds()))

    @property
    def state_label(self) -> str:
        if self.stale:
            return "STALE DATA"
        if self.source == "live":
            return "LIVE DATA"
        return "CACHED DATA"

    def as_cached(self) -> FleetSnapshot:
        return replace(self, source="cache")

    def as_stale(self, error: str | None = None) -> FleetSnapshot:
        return replace(
            self,
            source="stale",
            stale=True,
            last_error=error or self.last_error,
        )


@dataclass(slots=True)
class PageCursor:
    total: int
    index: int = 0

    def __post_init__(self) -> None:
        self.total = max(1, int(self.total))
        self.index = min(max(0, int(self.index)), self.total - 1)

    @property
    def label(self) -> str:
        return f"Page {self.index + 1}/{self.total}"

    @property
    def has_previous(self) -> bool:
        return self.index > 0

    @property
    def has_next(self) -> bool:
        return self.index < self.total - 1

    def previous(self) -> int:
        if self.has_previous:
            self.index -= 1
        return self.index

    def next(self) -> int:
        if self.has_next:
            self.index += 1
        return self.index


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(value: str) -> str:
    return "".join(
        character for character in value.upper().strip() if character.isalnum()
    )


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def chunks_by_length(lines: Iterable[str], max_length: int = 1000) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for line in lines:
        added = len(line) + (1 if current else 0)
        if current and current_length + added > max_length:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += added

    if current:
        chunks.append("\n".join(current))
    return chunks


def batches(values: Sequence[Any], size: int) -> list[Sequence[Any]]:
    safe_size = max(1, size)
    return [values[index : index + safe_size] for index in range(0, len(values), safe_size)]


def exact_or_partial(
    fleet: Iterable[Aircraft],
    query: str,
    fields: tuple[str, ...],
) -> list[Aircraft]:
    needle = normalize(query)
    exact: list[Aircraft] = []
    partial: list[Aircraft] = []

    for item in fleet:
        values = [normalize(getattr(item, field)) for field in fields]
        if needle in values:
            exact.append(item)
        elif any(needle and needle in value for value in values):
            partial.append(item)

    return exact or partial


def has_manage_guild(permissions: Any) -> bool:
    return bool(permissions and getattr(permissions, "manage_guild", False))
