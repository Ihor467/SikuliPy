"""Port of SikuliX exception hierarchy.

Java sources:
* SikuliXception.java  -> :class:`SikuliXception`
* SikuliException.java -> kept as alias
* FindFailed.java      -> :class:`FindFailed`
* FindFailedResponse.java -> :class:`FindFailedResponse`
* OculixTimeoutException.java -> :class:`OculixTimeout`
* ScreenOperationException.java -> :class:`ScreenOperationError`
"""

from __future__ import annotations

from enum import Enum


class SikuliXception(Exception):
    """Root exception type."""


class SikuliException(SikuliXception):
    """Alias for backward compatibility with SikuliX."""


class FindFailed(SikuliXception):
    """Raised when a find/wait call cannot locate the target."""


class OculixTimeout(SikuliXception):
    pass


class ScreenOperationError(SikuliXception):
    pass


class FindFailedResponse(Enum):
    ABORT = "abort"
    SKIP = "skip"
    PROMPT = "prompt"
    RETRY = "retry"
