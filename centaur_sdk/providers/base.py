"""Abstract base class for secret manager backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SecretManagerBackend(ABC):
    """Interface for secret manager storage backends.

    Each backend loads secrets into a ``dict[str, str]`` cache.  The service
    layer handles HTTP, auth, and the background refresh loop.
    """

    @abstractmethod
    async def load_all(self) -> dict[str, str]:
        """Load all secrets and return them as a key→value dict."""

    @property
    def supports_refresh(self) -> bool:
        """Whether this backend benefits from periodic refresh."""
        return True
