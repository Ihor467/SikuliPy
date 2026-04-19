"""SSH tunnel — Python port of ``com.sikulix.util.SSHTunnel`` (JSch).

Java used JSch for direct TCP port forwarding to reach a remote VNC
server behind a bastion host. The Python stack uses ``sshtunnel``
(which is a thin wrapper around ``paramiko``) for the same job.

Swappable backend: tests plug in a fake ``TunnelBackend`` that records
``open``/``close`` without touching the network.

Typical use::

    with SSHTunnel.open("10.0.0.5", "user", "secret") as tunnel:
        vnc = VNCScreen.start("127.0.0.1", tunnel.local_port)
        ...
"""

from __future__ import annotations

from typing import Protocol


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class TunnelBackend(Protocol):
    """An open forwarding session.

    ``local_port`` is the port on 127.0.0.1 clients should connect to.
    ``stop()`` tears the tunnel down.
    """

    @property
    def local_port(self) -> int: ...
    @property
    def is_active(self) -> bool: ...
    def stop(self) -> None: ...


class TunnelOpener(Protocol):
    def open(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_user: str,
        ssh_password: str | None,
        ssh_key_path: str | None,
        remote_host: str,
        remote_port: int,
        local_port: int,
    ) -> TunnelBackend: ...


# ---------------------------------------------------------------------------
# sshtunnel / paramiko implementation
# ---------------------------------------------------------------------------


class _SshtunnelBackend:
    """Adapter around a running ``sshtunnel.SSHTunnelForwarder``."""

    def __init__(self, forwarder) -> None:
        self._forwarder = forwarder

    @property
    def local_port(self) -> int:
        return int(self._forwarder.local_bind_port)

    @property
    def is_active(self) -> bool:
        return bool(getattr(self._forwarder, "is_active", False))

    def stop(self) -> None:
        try:
            self._forwarder.stop()
        except Exception:
            pass


class _SshtunnelOpener:
    def open(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_user: str,
        ssh_password: str | None,
        ssh_key_path: str | None,
        remote_host: str,
        remote_port: int,
        local_port: int,
    ) -> TunnelBackend:
        from sshtunnel import SSHTunnelForwarder  # type: ignore[import-not-found]

        kwargs: dict[str, object] = {
            "ssh_username": ssh_user,
            "remote_bind_address": (remote_host, remote_port),
        }
        # 0 lets sshtunnel auto-pick an ephemeral local port.
        kwargs["local_bind_address"] = ("127.0.0.1", int(local_port))
        if ssh_password is not None:
            kwargs["ssh_password"] = ssh_password
        if ssh_key_path is not None:
            kwargs["ssh_pkey"] = ssh_key_path
        forwarder = SSHTunnelForwarder((ssh_host, int(ssh_port)), **kwargs)
        forwarder.start()
        return _SshtunnelBackend(forwarder)


# ---------------------------------------------------------------------------
# Singleton opener — swappable for tests
# ---------------------------------------------------------------------------

_opener: TunnelOpener | None = None


def get_opener() -> TunnelOpener:
    global _opener
    if _opener is None:
        _opener = _SshtunnelOpener()
    return _opener


def set_opener(opener: TunnelOpener | None) -> None:
    global _opener
    _opener = opener


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


DEFAULT_SSH_PORT = 22
DEFAULT_VNC_PORT = 5900


class SSHTunnel:
    """Context-managed SSH local port forwarding (port of ``SSHTunnel.java``).

    The constructor does not open the tunnel. Use :meth:`open` (classmethod)
    for the common cases, or construct and call :meth:`start` explicitly.

    Attributes:
        local_port: the listening port on 127.0.0.1 after :meth:`start`.
        is_connected: whether the underlying SSH session is still active.
    """

    def __init__(
        self,
        ssh_host: str,
        ssh_user: str,
        ssh_password: str | None = None,
        *,
        ssh_port: int = DEFAULT_SSH_PORT,
        ssh_key_path: str | None = None,
        remote_host: str = "localhost",
        remote_port: int = DEFAULT_VNC_PORT,
        local_port: int = DEFAULT_VNC_PORT,
    ) -> None:
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_key_path = ssh_key_path
        self.remote_host = remote_host
        self.remote_port = remote_port
        self._requested_local_port = local_port
        self._backend: TunnelBackend | None = None

    # ---- Class-level factories (parity with SSHTunnel.java) ----------
    @classmethod
    def open(
        cls,
        ssh_host: str,
        ssh_user: str,
        ssh_password: str | None = None,
        *,
        ssh_port: int = DEFAULT_SSH_PORT,
        ssh_key_path: str | None = None,
        remote_host: str = "localhost",
        remote_port: int = DEFAULT_VNC_PORT,
        local_port: int = DEFAULT_VNC_PORT,
    ) -> "SSHTunnel":
        tunnel = cls(
            ssh_host,
            ssh_user,
            ssh_password,
            ssh_port=ssh_port,
            ssh_key_path=ssh_key_path,
            remote_host=remote_host,
            remote_port=remote_port,
            local_port=local_port,
        )
        tunnel.start()
        return tunnel

    @classmethod
    def open_auto_port(
        cls,
        ssh_host: str,
        ssh_user: str,
        ssh_password: str | None = None,
        *,
        ssh_port: int = DEFAULT_SSH_PORT,
        ssh_key_path: str | None = None,
        remote_host: str = "localhost",
        remote_port: int = DEFAULT_VNC_PORT,
    ) -> "SSHTunnel":
        return cls.open(
            ssh_host,
            ssh_user,
            ssh_password,
            ssh_port=ssh_port,
            ssh_key_path=ssh_key_path,
            remote_host=remote_host,
            remote_port=remote_port,
            local_port=0,
        )

    # ---- Lifecycle ---------------------------------------------------
    def start(self) -> "SSHTunnel":
        if self._backend is not None:
            return self
        self._backend = get_opener().open(
            self.ssh_host,
            self.ssh_port,
            self.ssh_user,
            self.ssh_password,
            self.ssh_key_path,
            self.remote_host,
            self.remote_port,
            self._requested_local_port,
        )
        return self

    def close(self) -> None:
        if self._backend is not None:
            self._backend.stop()
            self._backend = None

    # Context-manager sugar so `with SSHTunnel.open(...) as t:` works.
    def __enter__(self) -> "SSHTunnel":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---- Introspection ----------------------------------------------
    @property
    def local_port(self) -> int:
        if self._backend is None:
            raise RuntimeError("SSHTunnel is not started")
        return self._backend.local_port

    @property
    def is_connected(self) -> bool:
        return self._backend is not None and self._backend.is_active
