"""Port of VNCScreen.java + VNCRobot.java. Phase 5."""

from __future__ import annotations

from sikulipy.core.region import Region


class VNCScreen(Region):
    def __init__(self, host: str, port: int = 5900, password: str = "",
                 width: int = 1920, height: int = 1080) -> None:
        super().__init__(0, 0, width, height)
        self.host = host
        self.port = port
        self.password = password
        self.client = None  # set up in Phase 5

    @classmethod
    def start(cls, host: str, port: int = 5900, password: str = "",
              width: int = 1920, height: int = 1080) -> "VNCScreen":
        raise NotImplementedError("Phase 5")

    def stop(self) -> None:
        raise NotImplementedError("Phase 5")
