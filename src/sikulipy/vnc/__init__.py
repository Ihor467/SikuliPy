"""VNC remote automation.

Ports ``org.sikuli.vnc`` (VNCScreen, VNCRobot) and the TigerVNC helpers
(VNCClient, VNCFrameBuffer, VNCClipboard, XKeySym, ThreadLocalSecurityClient).
Backed by ``vncdotool`` in phase 5, with a custom asyncio RFB client as a
possible follow-up.
"""

from sikulipy.vnc.screen import VNCScreen

__all__ = ["VNCScreen"]
