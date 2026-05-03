"""Filter the discovered element list by :class:`ElementKind`.

Pure data — the IDE's checkbox column owns one toggle per kind, and
this module turns those toggles into a predicate that narrows the
displayed list. Default state: every kind disabled (the user opts in
to the kinds they want outlined; cuts noise on dense pages).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sikulipy.web.elements import ElementKind, WebElement


@dataclass
class ElementFilter:
    """Holds the set of currently enabled :class:`ElementKind`s."""

    kinds: set[ElementKind] = field(default_factory=set)

    def enable(self, kind: ElementKind) -> None:
        self.kinds.add(kind)

    def disable(self, kind: ElementKind) -> None:
        self.kinds.discard(kind)

    def toggle(self, kind: ElementKind, on: bool) -> None:
        if on:
            self.enable(kind)
        else:
            self.disable(kind)

    def is_enabled(self, kind: ElementKind) -> bool:
        return kind in self.kinds

    def apply(self, elements: Iterable[WebElement]) -> list[WebElement]:
        """Return the subset of ``elements`` whose kind is enabled."""
        return [e for e in elements if e.visible and e.kind in self.kinds]
