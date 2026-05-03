"""Headless model for the Web Auto URL prompt.

The Flet dialog wraps this with a TextField + OK/Cancel buttons. The
model lives here so unit tests can drive the validation logic without
spinning up a window. Mirrors the split between :mod:`ide.capture`
(headless model) and :mod:`ide.app` (Flet view).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class WebAutoDialog:
    """Holds the URL the user typed + the validation message."""

    text: str = ""
    error: str | None = None

    def set_text(self, value: str) -> None:
        self.text = (value or "").strip()
        self.error = None

    def normalize(self) -> str | None:
        """Return a usable URL or ``None`` (with :attr:`error` set).

        Accepts ``http(s)://...`` directly. A bare host like
        ``example.com`` is upgraded to ``https://example.com`` so the
        user doesn't have to type the scheme. ``javascript:``,
        ``data:``, and other unsafe schemes are rejected.
        """
        raw = self.text.strip()
        if not raw:
            self.error = "URL is required"
            return None
        # Reject single-colon schemes like ``javascript:`` / ``data:`` /
        # ``file:`` before we second-guess the user with an https://
        # upgrade, otherwise ``javascript:alert(1)`` would silently
        # become ``https://javascript:alert(1)``.
        head = raw.split(":", 1)[0].lower()
        if ":" in raw and "://" not in raw and head in _UNSAFE_BARE_SCHEMES:
            self.error = f"unsupported scheme: {head!r}"
            return None
        # Bare host fast-path — let "example.com/x" through too.
        if "://" not in raw:
            raw = "https://" + raw
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            self.error = f"unsupported scheme: {parsed.scheme!r}"
            return None
        if not parsed.netloc:
            self.error = "URL is missing a hostname"
            return None
        self.error = None
        return raw


_UNSAFE_BARE_SCHEMES = {
    "javascript",
    "data",
    "file",
    "about",
    "vbscript",
    "ftp",
    "ws",
    "wss",
}
