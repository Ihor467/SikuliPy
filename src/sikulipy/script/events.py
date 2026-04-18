"""Event model — ports ObserveEvent, ObserverCallBack, SikuliEvent, ImageCallback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ObserveEventType(Enum):
    APPEAR = "appear"
    VANISH = "vanish"
    CHANGE = "change"
    GENERIC = "generic"


@dataclass
class ObserveEvent:
    type: ObserveEventType
    region: Any
    match: Any | None = None
    data: Any | None = None


ObserverCallback = Callable[[ObserveEvent], None]
