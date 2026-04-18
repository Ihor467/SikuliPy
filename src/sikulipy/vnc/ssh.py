"""SSH tunnel — port of com.sikulix.util.SSHTunnel (jcraft/jsch wrapper).

Python will use ``sshtunnel`` or ``paramiko`` directly. Phase 5.
"""

from __future__ import annotations


class SSHTunnel:
    def __init__(self, user: str, host: str, port: int = 22, password: str | None = None,
                 key_path: str | None = None) -> None:
        self.user = user
        self.host = host
        self.port = port
        self.password = password
        self.key_path = key_path

    def open(self, local_port: int, remote_host: str, remote_port: int) -> None:
        raise NotImplementedError("Phase 5")

    def close(self) -> None:
        raise NotImplementedError("Phase 5")
