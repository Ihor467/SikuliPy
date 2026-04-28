"""Drive an Android tablet from SikuliPy over USB or Wi-Fi ADB.

Usage::

    # USB (tablet plugged in, USB debugging enabled):
    uv run python examples/tablet_demo.py

    # Specific USB device when more than one is attached:
    uv run python examples/tablet_demo.py --serial ABCDEF1234

    # Wi-Fi ADB (Android <= 10, after `adb tcpip 5555` over USB once):
    uv run python examples/tablet_demo.py --address 192.168.1.50:5555

    # Wi-Fi ADB (Android 11+, after a one-time `adb pair` from your shell):
    uv run python examples/tablet_demo.py --address 192.168.1.50:39733

The script:
  1. Connects to the tablet (USB or Wi-Fi).
  2. Saves a full-device screenshot to ``examples/tablet_screenshot.png``.
  3. Optionally clicks a pattern image you supply with ``--pattern``.
  4. Optionally types text with ``--type``.

Requires the ``android`` extra::

    uv pip install -e ".[android]"

and the ``adb`` binary on PATH (``sudo apt install adb`` on Debian/Ubuntu).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sikulipy.android.screen import ADBScreen
from sikulipy.core.pattern import Pattern


def _build_screen(args: argparse.Namespace) -> ADBScreen:
    """Pick USB or Wi-Fi based on whether ``--address`` was passed."""
    if args.address:
        print(f"Connecting over Wi-Fi to {args.address} …")
        return ADBScreen.connect(args.address)
    print(
        "Connecting over USB"
        + (f" to serial {args.serial}" if args.serial else " (first attached device)")
        + " …"
    )
    return ADBScreen.start(serial=args.serial)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SikuliPy Android demo")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--serial",
        help="USB device serial (use when multiple devices are attached)",
    )
    group.add_argument(
        "--address",
        help="Wi-Fi ADB address, e.g. 192.168.1.50:5555",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).with_name("tablet_screenshot.png"),
        help="Where to save the screenshot",
    )
    parser.add_argument(
        "--pattern",
        type=Path,
        help="PNG to find and tap on the device (optional)",
    )
    parser.add_argument(
        "--type",
        dest="text",
        help="Text to send via 'input text' after the tap (optional)",
    )
    args = parser.parse_args(argv)

    screen = _build_screen(args)
    w, h = screen.w, screen.h
    print(f"Connected: {screen.device.serial}  ({w}x{h})")

    # 1. Screenshot — useful even on its own to verify the connection.
    screen.device.screencap()  # warm the path
    png = screen.device.screencap_png()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(png)
    print(f"Saved screenshot to {args.out}")

    # 2. Tap a pattern if given. ADBScreen.click reuses the desktop find()
    #    pipeline against the device screencap, then dispatches `input tap`.
    if args.pattern:
        if not args.pattern.exists():
            print(f"Pattern not found: {args.pattern}", file=sys.stderr)
            return 2
        try:
            screen.click(Pattern(str(args.pattern)))
            print(f"Tapped pattern: {args.pattern.name}")
        except Exception as exc:
            print(f"Pattern not visible on screen: {exc}", file=sys.stderr)
            return 3

    # 3. Type text via 'input text' (spaces become %s automatically inside
    #    ADBDevice.input_text — no shell-escaping headaches).
    if args.text:
        screen.type(args.text)
        print(f"Typed: {args.text!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
