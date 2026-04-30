"""Centaur crypto-aware chart helpers.

Brand-color resolution lives here so any chart that names a token, chain,
protocol, stablecoin, or notable event auto-resolves to the canonical hex
without the agent having to remember it.
"""

from .brand_colors import (
    CHAIN_COLORS,
    EVENT_COLORS,
    PROTOCOL_COLORS,
    STABLECOIN_COLORS,
    TOKEN_COLORS,
    color_for,
    is_brand_known,
    palette_for,
)

__all__ = [
    "CHAIN_COLORS",
    "EVENT_COLORS",
    "PROTOCOL_COLORS",
    "STABLECOIN_COLORS",
    "TOKEN_COLORS",
    "color_for",
    "is_brand_known",
    "palette_for",
]
