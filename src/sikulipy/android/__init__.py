"""Android automation via ADB.

Ports ``org.sikuli.android`` (ADBClient, ADBDevice, ADBRobot, ADBScreen).
Backed by ``pure-python-adb`` or a direct socket client. Phase 4.
"""

from sikulipy.android._backend import get_client, set_client
from sikulipy.android.client import ADBClient, ADBDevice
from sikulipy.android.screen import ADBScreen

__all__ = ["ADBClient", "ADBDevice", "ADBScreen", "get_client", "set_client"]
