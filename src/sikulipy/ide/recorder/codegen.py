"""Source-line generators for recorded actions.

OculiX has Jython, Java, and Robot Framework targets behind an
``ICodeGenerator`` interface. We start with Python only (the SikuliPy
default) and keep the shape so a Robot/Java generator can drop in
without refactoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sikulipy.ide.recorder.workflow import RecorderAction


@dataclass(frozen=True)
class GenInput:
    """Per-line input to a generator.

    ``pattern`` is the basename of the saved PNG (e.g. ``btn.png``) and
    is required for image-bearing actions. ``payload`` carries the
    text/key/seconds for non-pattern actions. ``timeout`` is the wait
    upper bound; ``similarity`` is an optional override (``None`` =
    leave the call to default similarity).
    """

    pattern: str | None = None
    pattern2: str | None = None  # second pattern for drag_drop / swipe
    payload: str | None = None
    timeout: float = 10.0
    similarity: float | None = None


class CodeGenerator(Protocol):
    name: str

    def header(self) -> str: ...

    def generate(self, action: RecorderAction, gi: GenInput) -> str: ...


def _pattern_expr(pattern: str, similarity: float | None) -> str:
    if similarity is None:
        return f'Pattern("{pattern}")'
    return f'Pattern("{pattern}").similar({similarity:g})'


@dataclass
class PythonGenerator:
    """Default generator — emits SikuliPy/Jython-compatible calls."""

    name: str = "python"

    def header(self) -> str:
        return "from sikulipy import *\n"

    def generate(self, action: RecorderAction, gi: GenInput) -> str:
        if action.needs_pattern:
            if not gi.pattern:
                raise ValueError(f"{action.value} needs a pattern")
            pat = _pattern_expr(gi.pattern, gi.similarity)
            t = _fmt_num(gi.timeout)
            if action is RecorderAction.CLICK:
                return f"wait({pat}, {t}).click()"
            if action is RecorderAction.DBLCLICK:
                return f"wait({pat}, {t}).doubleClick()"
            if action is RecorderAction.RCLICK:
                return f"wait({pat}, {t}).rightClick()"
            if action is RecorderAction.WAIT:
                return f"wait({pat}, {t})"
            if action is RecorderAction.WAIT_VANISH:
                return f"waitVanish({pat}, {t})"

        if action.needs_two_patterns:
            if not gi.pattern or not gi.pattern2:
                raise ValueError(f"{action.value} needs two patterns")
            src = _pattern_expr(gi.pattern, gi.similarity)
            dst = _pattern_expr(gi.pattern2, gi.similarity)
            t = _fmt_num(gi.timeout)
            if action is RecorderAction.DRAG_DROP:
                return f"dragDrop(wait({src}, {t}), wait({dst}, {t}))"
            if action is RecorderAction.SWIPE:
                return (
                    f"Screen().swipe(wait({src}, {t}), wait({dst}, {t}))"
                )

        if action is RecorderAction.WHEEL:
            if not gi.payload:
                raise ValueError("wheel needs a payload")
            direction, steps = _parse_wheel_payload(gi.payload)
            return f"wheel({direction}, {steps})"
        if action is RecorderAction.TYPE:
            text = gi.payload or ""
            return f"type({_py_str(text)})"
        if action is RecorderAction.KEY_COMBO:
            # payload format: "CTRL+SHIFT+c" → modifiers + final key
            if not gi.payload:
                raise ValueError("key_combo needs a payload")
            return _gen_key_combo(gi.payload)
        if action is RecorderAction.PAUSE:
            secs = gi.payload or "1"
            return f"sleep({_fmt_num(float(secs))})"
        if action is RecorderAction.LAUNCH_APP:
            if not gi.payload:
                raise ValueError("launch_app needs a payload")
            name_lit = _py_str(gi.payload)
            var = _app_var(gi.payload)
            # Two-statement block: open the process, then move keyboard
            # focus to its window so the next recorded keystrokes go to
            # the right app. Emitted as a single string with a real
            # newline; the editor inserter handles surrounding newlines.
            return f"{var} = App.open({name_lit})\n{var}.focus()"
        if action is RecorderAction.CLOSE_APP:
            if not gi.payload:
                raise ValueError("close_app needs a payload")
            name_lit = _py_str(gi.payload)
            # Close by title rather than via a held handle, since the
            # handle from a prior Launch may not be in scope here.
            return f"App.find({name_lit}).close()"
        if action is RecorderAction.TEXT_CLICK:
            if not gi.payload:
                raise ValueError("text_click needs a payload")
            return f"click(findText({_py_str(gi.payload)}))"
        if action is RecorderAction.TEXT_WAIT:
            if not gi.payload:
                raise ValueError("text_wait needs a payload")
            return f"wait(findText({_py_str(gi.payload)}), {_fmt_num(gi.timeout)})"
        if action is RecorderAction.TEXT_EXISTS:
            if not gi.payload:
                raise ValueError("text_exists needs a payload")
            return f"exists(findText({_py_str(gi.payload)}), {_fmt_num(gi.timeout)})"

        raise ValueError(f"unknown action: {action}")


def _fmt_num(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return f"{n:g}"


def _app_var(name: str) -> str:
    """Derive a Python identifier from an app name. Falls back to
    ``app`` when the name has no usable letters (e.g. ``./bin/x``)."""
    base = Path(name).name if "/" in name or "\\" in name else name
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in base.lower())
    cleaned = cleaned.lstrip("_0123456789")
    return cleaned or "app"


def _py_str(s: str) -> str:
    # Always double-quote, escape backslashes and the quote char.
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_MODIFIER_NAMES = {
    "ctrl": "KeyModifier.CTRL",
    "control": "KeyModifier.CTRL",
    "alt": "KeyModifier.ALT",
    "shift": "KeyModifier.SHIFT",
    "cmd": "KeyModifier.CMD",
    "win": "KeyModifier.WIN",
    "meta": "KeyModifier.META",
}


def _gen_key_combo(combo: str) -> str:
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("key_combo payload is empty")
    *mods, key = parts
    mod_exprs = []
    for m in mods:
        try:
            mod_exprs.append(_MODIFIER_NAMES[m.lower()])
        except KeyError:
            raise ValueError(f"unknown modifier {m!r}") from None
    if len(key) == 1:
        key_expr = _py_str(key)
    else:
        key_expr = f"Key.{key.upper()}"
    if not mod_exprs:
        return f"type({key_expr})"
    return f"type({key_expr}, {' | '.join(mod_exprs)})"


_WHEEL_DIRECTIONS = {
    "up": -1,
    "down": 1,
    "-1": -1,
    "1": 1,
}


def _parse_wheel_payload(payload: str) -> tuple[int, int]:
    """Parse "up 3" / "down" / "1,5" / "-1 2" into (direction, steps).

    Direction is normalized to ``-1`` (up) or ``1`` (down). Steps default
    to 1. Raises ``ValueError`` on bad input.
    """
    parts = [p for p in payload.replace(",", " ").split() if p]
    if not parts:
        raise ValueError("wheel payload is empty")
    head = parts[0].lower()
    if head not in _WHEEL_DIRECTIONS:
        raise ValueError(f"unknown wheel direction {parts[0]!r} (use up/down/-1/1)")
    direction = _WHEEL_DIRECTIONS[head]
    steps = 1
    if len(parts) > 1:
        try:
            steps = int(parts[1])
        except ValueError:
            raise ValueError(f"bad wheel step count {parts[1]!r}") from None
        if steps < 1:
            raise ValueError("wheel steps must be >= 1")
    return direction, steps


def default_generator() -> CodeGenerator:
    return PythonGenerator()
