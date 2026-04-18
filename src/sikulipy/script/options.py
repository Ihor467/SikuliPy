"""Port of ``org.sikuli.script.Options`` — settings and configuration store."""

from __future__ import annotations

from pydantic import BaseModel


class Options(BaseModel):
    min_similarity: float = 0.7
    wait_before_action: float = 0.3
    auto_wait_timeout: float = 3.0
    move_mouse_delay: float = 0.5
    screen_highlight_duration: float = 2.0
    image_path: list[str] = []
