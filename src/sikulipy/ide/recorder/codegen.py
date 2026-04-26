"""Source-line generators for recorded actions.

OculiX has Jython, Java, and Robot Framework targets behind an
``ICodeGenerator`` interface. We start with Python only (the SikuliPy
default) and keep the shape so a Robot/Java generator can drop in
without refactoring.
"""

from __future__ import annotations

from dataclasses import dataclass
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

        raise ValueError(f"unknown action: {action}")


def _fmt_num(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return f"{n:g}"


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


def default_generator() -> CodeGenerator:
    return PythonGenerator()
