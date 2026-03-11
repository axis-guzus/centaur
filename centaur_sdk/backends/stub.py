"""Backend that returns key names as stub values for firewall injection.

In server mode, tools never see real secrets. They receive the key name
itself (e.g. ``secret("ALCHEMY_API_KEY")`` → ``"ALCHEMY_API_KEY"``).
The outbound HTTPS request carries this stub in a header, and the
firewall (mitmproxy) replaces it with the real secret before it leaves
the network.
"""

from __future__ import annotations

from centaur_sdk.backends.base import SecretBackend


class StubBackend(SecretBackend):
    """Return the key name itself as the value.

    This is the server-mode default. Tools put the stub in HTTP headers,
    and the firewall replaces it with the real credential in-flight.
    """

    async def get(self, key: str) -> str | None:
        return key

    async def list_keys(self) -> list[str]:
        return []
