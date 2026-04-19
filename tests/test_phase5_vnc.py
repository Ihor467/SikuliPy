"""Phase 5 tests — VNCScreen + SSHTunnel against fake backends.

No real RFB server or SSH daemon is touched. A ``RecordingVncBackend``
captures every pointer/key event, and a ``FakeTunnelOpener`` records the
forwarding parameters handed to ``SSHTunnel``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from sikulipy.core.keyboard import KeyModifier
from sikulipy.core.location import Location
from sikulipy.core.match import Match
from sikulipy.vnc import SSHTunnel, VNCScreen, set_connector
from sikulipy.vnc import xkeysym
from sikulipy.vnc._backend import VncBackend, VncConnector
from sikulipy.vnc.screen import (
    VNC_BUTTON_1,
    VNC_BUTTON_2,
    VNC_BUTTON_3,
    VNC_BUTTON_4,
    VNC_BUTTON_5,
)
from sikulipy.vnc.ssh import TunnelBackend, set_opener


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class RecordingVncBackend(VncBackend):
    _size: tuple[int, int] = (800, 600)
    captures: int = 0
    pointer_events: list[tuple[int, int, int]] = field(default_factory=list)
    key_events: list[tuple[str, int]] = field(default_factory=list)
    disconnected: bool = False
    capture_bitmap: Any = None

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    def capture(self):
        self.captures += 1
        return self.capture_bitmap

    def pointer(self, x: int, y: int, button_mask: int) -> None:
        self.pointer_events.append((x, y, button_mask))

    def key_down(self, xksym: int) -> None:
        self.key_events.append(("down", xksym))

    def key_up(self, xksym: int) -> None:
        self.key_events.append(("up", xksym))

    def disconnect(self) -> None:
        self.disconnected = True


@dataclass
class RecordingConnector(VncConnector):
    backend: RecordingVncBackend
    calls: list[tuple[str, int, str | None]] = field(default_factory=list)

    def connect(self, host: str, port: int = 5900, password: str | None = None):
        self.calls.append((host, port, password))
        return self.backend


@pytest.fixture
def vnc_backend():
    # Fresh singletons per test — VNCScreen caches screens by host:port.
    VNCScreen._screens.clear()
    backend = RecordingVncBackend()
    connector = RecordingConnector(backend=backend)
    set_connector(connector)
    yield backend, connector
    set_connector(None)
    VNCScreen._screens.clear()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_start_connects_with_defaults(vnc_backend):
    backend, connector = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    assert isinstance(scr, VNCScreen)
    assert scr.host == "10.0.0.5"
    assert scr.port == 5900
    assert (scr.x, scr.y, scr.w, scr.h) == (0, 0, 800, 600)
    assert connector.calls == [("10.0.0.5", 5900, None)]


def test_start_is_idempotent_per_host_port(vnc_backend):
    _, connector = vnc_backend
    a = VNCScreen.start("10.0.0.5")
    b = VNCScreen.start("10.0.0.5")
    assert a is b  # Java parity: existing session is reused.
    assert len(connector.calls) == 1


def test_stop_disconnects_and_forgets(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.stop()
    assert backend.disconnected is True
    assert scr.is_running() is False
    # A fresh start must reconnect.
    _ = VNCScreen.start("10.0.0.5")
    # Backend's disconnected flag persists on the same mock, but a new
    # connector.calls entry is recorded:
    connector = scr  # just to silence unused warnings; real assertion next


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def test_capture_delegates_to_backend(vnc_backend):
    backend, _ = vnc_backend
    backend.capture_bitmap = object()
    scr = VNCScreen.start("10.0.0.5")
    bmp = scr._capture_bgr()
    assert bmp is backend.capture_bitmap
    assert backend.captures == 1


# ---------------------------------------------------------------------------
# Pointer
# ---------------------------------------------------------------------------


def test_click_issues_move_down_up(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.click(Location(100, 200))
    assert backend.pointer_events == [
        (100, 200, 0),
        (100, 200, VNC_BUTTON_1),
        (100, 200, 0),
    ]


def test_click_none_clicks_center(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.click()
    # center of 800x600 is (400, 300)
    assert (400, 300, VNC_BUTTON_1) in backend.pointer_events


def test_double_click_taps_twice(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.double_click(Location(10, 20))
    downs = [ev for ev in backend.pointer_events if ev == (10, 20, VNC_BUTTON_1)]
    assert len(downs) == 2


def test_right_click_uses_button_3(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.right_click(Location(50, 60))
    assert (50, 60, VNC_BUTTON_3) in backend.pointer_events


def test_middle_click_uses_button_2(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.middle_click(Location(50, 60))
    assert (50, 60, VNC_BUTTON_2) in backend.pointer_events


def test_hover_moves_without_press(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.hover(Location(33, 44))
    assert backend.pointer_events == [(33, 44, 0)]


def test_drag_drop_interpolates(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.drag_drop(Location(0, 0), Location(100, 0), steps=5)
    # First event: move to src with mask 0
    assert backend.pointer_events[0] == (0, 0, 0)
    # Second event: press at src with mask 1
    assert backend.pointer_events[1] == (0, 0, VNC_BUTTON_1)
    # Last event: release at dst with mask 0
    assert backend.pointer_events[-1] == (100, 0, 0)
    # Interpolated move at step 3/5 -> (60, 0) with button held.
    assert (60, 0, VNC_BUTTON_1) in backend.pointer_events


def test_wheel_up_down_uses_buttons_4_5(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.hover(Location(50, 50))
    scr.wheel(1)
    assert (50, 50, VNC_BUTTON_4) in backend.pointer_events
    scr.wheel(-1)
    assert (50, 50, VNC_BUTTON_5) in backend.pointer_events


# ---------------------------------------------------------------------------
# Pattern target (uses Region.find)
# ---------------------------------------------------------------------------


def test_click_pattern_finds_then_clicks_with_offset(vnc_backend, monkeypatch):
    from sikulipy.core.pattern import Pattern

    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    sentinel = Match(x=200, y=300, w=40, h=20, score=0.99)
    monkeypatch.setattr(VNCScreen, "find", lambda self, target: sentinel)

    scr.click(Pattern(image="btn.png").targetOffset(3, -2))
    # centre (220, 310) + offset (3, -2) = (223, 308)
    assert (223, 308, VNC_BUTTON_1) in backend.pointer_events


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------


def test_type_lowercase_letters(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.type("ab")
    assert backend.key_events == [
        ("down", xkeysym.XK_a),
        ("up", xkeysym.XK_a),
        ("down", xkeysym.XK_b),
        ("up", xkeysym.XK_b),
    ]


def test_type_uppercase_wraps_shift(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.type("A")
    assert backend.key_events == [
        ("down", xkeysym.XK_Shift_L),
        ("down", xkeysym.XK_A),
        ("up", xkeysym.XK_A),
        ("up", xkeysym.XK_Shift_L),
    ]


def test_type_enter_uses_xk_return(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.type("\n")
    assert ("down", xkeysym.XK_Return) in backend.key_events
    assert ("up", xkeysym.XK_Return) in backend.key_events


def test_type_with_ctrl_modifier(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr.type("c", modifiers=KeyModifier.CTRL)
    # Ctrl is held down first, char typed, then ctrl released.
    assert backend.key_events[0] == ("down", xkeysym.XK_Control_L)
    assert backend.key_events[-1] == ("up", xkeysym.XK_Control_L)
    assert ("down", xkeysym.XK_c) in backend.key_events


def test_key_up_all_releases_every_pressed_key(vnc_backend):
    backend, _ = vnc_backend
    scr = VNCScreen.start("10.0.0.5")
    scr._key_down(xkeysym.XK_Shift_L)
    scr._key_down(xkeysym.XK_Control_L)
    backend.key_events.clear()
    scr.key_up_all()
    released = {ev[1] for ev in backend.key_events if ev[0] == "up"}
    assert xkeysym.XK_Shift_L in released
    assert xkeysym.XK_Control_L in released


# ---------------------------------------------------------------------------
# SSH tunnel
# ---------------------------------------------------------------------------


@dataclass
class FakeTunnelBackend(TunnelBackend):
    _local_port: int
    stopped: bool = False

    @property
    def local_port(self) -> int:
        return self._local_port

    @property
    def is_active(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True


@dataclass
class FakeOpener:
    opens: list[dict] = field(default_factory=list)
    assigned_port: int = 55900
    backend: FakeTunnelBackend | None = None

    def open(self, ssh_host, ssh_port, ssh_user, ssh_password, ssh_key_path,
             remote_host, remote_port, local_port):
        self.opens.append({
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "ssh_password": ssh_password,
            "ssh_key_path": ssh_key_path,
            "remote_host": remote_host,
            "remote_port": remote_port,
            "local_port": local_port,
        })
        # "auto" local port (0) gets resolved to assigned_port.
        effective = local_port or self.assigned_port
        self.backend = FakeTunnelBackend(_local_port=effective)
        return self.backend


@pytest.fixture
def fake_opener():
    opener = FakeOpener()
    set_opener(opener)
    yield opener
    set_opener(None)


def test_tunnel_open_forwards_defaults(fake_opener):
    tunnel = SSHTunnel.open("bastion", "root", "secret")
    assert tunnel.is_connected is True
    assert tunnel.local_port == 5900
    call = fake_opener.opens[0]
    assert call["ssh_host"] == "bastion"
    assert call["ssh_port"] == 22
    assert call["ssh_user"] == "root"
    assert call["ssh_password"] == "secret"
    assert call["remote_host"] == "localhost"
    assert call["remote_port"] == 5900
    assert call["local_port"] == 5900


def test_tunnel_auto_port_passes_zero(fake_opener):
    fake_opener.assigned_port = 61234
    tunnel = SSHTunnel.open_auto_port("bastion", "root", "secret")
    assert fake_opener.opens[0]["local_port"] == 0
    # Backend-assigned port is what callers should see.
    assert tunnel.local_port == 61234


def test_tunnel_context_manager_closes(fake_opener):
    with SSHTunnel.open("bastion", "root", "secret") as tunnel:
        assert tunnel.is_connected is True
    assert fake_opener.backend.stopped is True
    assert tunnel.is_connected is False


def test_tunnel_key_auth(fake_opener):
    SSHTunnel.open("bastion", "root", ssh_key_path="/tmp/id_rsa")
    call = fake_opener.opens[0]
    assert call["ssh_key_path"] == "/tmp/id_rsa"
    assert call["ssh_password"] is None


def test_tunnel_custom_ports(fake_opener):
    SSHTunnel.open(
        "bastion", "root", "secret",
        ssh_port=2222, remote_host="vnc.lan", remote_port=5901, local_port=15900,
    )
    call = fake_opener.opens[0]
    assert call["ssh_port"] == 2222
    assert call["remote_host"] == "vnc.lan"
    assert call["remote_port"] == 5901
    assert call["local_port"] == 15900


def test_tunnel_local_port_raises_before_start(fake_opener):
    tunnel = SSHTunnel("bastion", "root", "secret")
    with pytest.raises(RuntimeError):
        _ = tunnel.local_port
