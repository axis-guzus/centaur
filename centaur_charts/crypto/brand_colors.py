"""Brand-color resolver for crypto charts.

Every named token / chain / protocol / stablecoin / event resolves to its
canonical hex via :func:`color_for`. The resolver is case- and alias-insensitive
("ETH", "Ethereum", "weth", "wrapped-eth" all map to #627EEA on light, brightened
in dark mode).

Sources synthesised from:
    * Dune Analytics' canonical `color-palettes` repository (token + chain ids).
    * Each protocol's official brand kit (Aave, Uniswap, Lido, Pendle, etc.).
    * The Centaur crypto-charting style spec (see `.agents/skills/charting/STYLE.md`).

When a name is unknown, the resolver returns ``None`` so the caller can
fall back to the categorical Okabe-Ito cycle. Use :func:`palette_for` to get
a deterministic colour for any name (known brand → brand colour;
unknown name → cycle slot picked by hash for stability across renders).
"""

from __future__ import annotations

from ..style import OKABE_ITO, OKABE_ITO_DARK, ThemeMode, current_mode


# ── Tokens ──────────────────────────────────────────────────────────────────

# Light-mode hex; the dark-mode variant is auto-derived (lighten ~10-15% L for
# deep cool hues; warm hues unchanged) by ``_dark_swap``. Add explicit dark
# overrides only when the simple swap looks wrong.

TOKEN_COLORS: dict[str, str] = {
    "btc": "#F7931A",
    "eth": "#627EEA",
    "usdc": "#2775CA",
    "usdt": "#26A17B",
    "bnb": "#F3BA2F",
    "sol": "#14F195",
    "xrp": "#00AAE4",
    "doge": "#C2A633",
    "ada": "#0033AD",
    "trx": "#EB0029",
    "avax": "#E84142",
    "link": "#2A5ADA",
    "matic": "#8247E5",
    "pol": "#8247E5",  # Polygon's rebrand
    "dot": "#E6007A",
    "ltc": "#345D9D",
    "bch": "#8DC351",
    "ton": "#0098EA",
    "dai": "#F5AC37",
    "atom": "#2E3148",
    "near": "#00EC97",
    "apt": "#00C296",
    "sui": "#4DA2FF",
    "arb": "#28A0F0",
    "op": "#FF0420",
    "hype": "#98FCE4",
    "wld": "#5C5A58",
    "tao": "#6E45E2",
    "kas": "#6FC7BA",
    "rndr": "#CF1FFF",
    "inj": "#00F2FE",
    "icp": "#29ABE2",
    "fil": "#0090FF",
    "sei": "#9E201B",
    "uni": "#FF007A",
    "aave": "#B6509E",
    "comp": "#00D395",
    "mkr": "#1AAB9B",
    "crv": "#FF0000",
    "ldo": "#00A3FF",
    "rpl": "#FB7575",
    "bal": "#1E1E1E",
    "pendle": "#259D6F",
    "gmx": "#4CAFAA",
    "snx": "#00D1FF",
    "1inch": "#1B314F",
    "sushi": "#FA52A0",
    "cake": "#1FC7D4",
    "dydx": "#6966FF",
    "frax": "#000000",
    "yfi": "#006AE3",
    "cvx": "#1683CB",
    "ena": "#000000",
    "pyusd": "#003087",
    "lusd": "#2EB6E1",
    "usds": "#1AAB9B",
    "ondo": "#1B6AFF",
    "render": "#CF1FFF",
}


# ── Chains / networks ───────────────────────────────────────────────────────

CHAIN_COLORS: dict[str, str] = {
    "bitcoin": "#F7931A",
    "ethereum": "#627EEA",
    "solana": "#14F195",  # gradient anchor (#9945FF -> #14F195)
    "bnb": "#F3BA2F",
    "bnbchain": "#F3BA2F",
    "binance": "#F3BA2F",
    "avalanche": "#E84142",
    "tron": "#EB0029",
    "ton": "#0098EA",
    "sui": "#4DA2FF",
    "near": "#00EC97",
    "aptos": "#00C296",
    "cardano": "#0033AD",
    "cosmos": "#2E3148",
    "polkadot": "#E6007A",
    "sei": "#9E201B",
    "berachain": "#FF6B00",
    "hyperliquid": "#98FCE4",
    "arbitrum": "#28A0F0",
    "optimism": "#FF0420",
    "base": "#0052FF",
    "polygon": "#8247E5",
    "polygon-zkevm": "#A128C5",
    "linea": "#61DFFF",
    "scroll": "#EBC28E",
    "zksync": "#1E69FF",
    "starknet": "#E77786",
    "blast": "#FCFC03",
    "mantle": "#68CDB0",
    "mode": "#DFFE00",
    "zora": "#3A6DEB",
    "world": "#5C5A58",
    "ink": "#5E2AF3",
    "unichain": "#FC0FA4",
    "soneium": "#1A29D4",
    "abstract": "#2FBF7A",
    "monad": "#836EF9",
    "sonic": "#F27A2C",
    "fantom": "#1969FF",
}


# ── Protocols ───────────────────────────────────────────────────────────────

PROTOCOL_COLORS: dict[str, str] = {
    "uniswap": "#FF007A",
    "aave": "#B6509E",
    "aave-v2": "#2EBAC6",
    "aave-v3": "#B6509E",
    "compound": "#00D395",
    "makerdao": "#1AAB9B",
    "sky": "#1AAB9B",
    "curve": "#FF0000",
    "lido": "#00A3FF",
    "rocketpool": "#FB7575",
    "balancer": "#1E1E1E",
    "pendle": "#259D6F",
    "gmx": "#4CAFAA",
    "synthetix": "#00D1FF",
    "1inch": "#1B314F",
    "sushiswap": "#FA52A0",
    "pancakeswap": "#1FC7D4",
    "dydx": "#6966FF",
    "frax": "#000000",
    "yearn": "#006AE3",
    "convex": "#1683CB",
    "stargate": "#001AFF",
    "across": "#FF6B0E",
    "hop": "#B26EFF",
    "ondo": "#1B6AFF",
    "ethena": "#000000",
    "polymarket": "#00B574",
    "kalshi": "#008060",
    "morpho": "#0058D7",
    "spark": "#0042B0",
    "etherfi": "#00C2FF",
    "renzo": "#00B0FF",
    "kelp": "#7DD2FF",
    "eigenlayer": "#0F1115",
    "symbiotic": "#7E5BFF",
    "babylon": "#FF6F0F",
    "jito": "#A86CFF",
    "marinade": "#3CCDDA",
    "blackrock": "#000000",
    "fidelity": "#00874E",
}


# ── Stablecoins (semantic, when not using brand) ────────────────────────────

STABLECOIN_CLASS_COLORS = {
    "usd_tier": "#27AE60",       # green: directly USD-backed (USDC, PYUSD, EURC)
    "off_chain": "#2980B9",      # blue: off-chain reserves (USDT)
    "cdp": "#F39C12",            # orange: crypto-collateralized (DAI, crvUSD, GHO)
    "algo": "#E74C3C",           # red: algorithmic / synthetic (USDe, FRAX)
}

STABLECOIN_COLORS: dict[str, str] = {
    "usdt": "#26A17B",
    "usdc": "#2775CA",
    "dai": "#F5AC37",
    "frax": "#000000",
    "crvusd": "#FF0000",
    "gho": "#B6509E",
    "usde": "#000000",
    "pyusd": "#003087",
    "lusd": "#2EB6E1",
    "usds": "#1AAB9B",
    "tusd": "#002868",
    "busd": "#F0B90B",
    "fdusd": "#5DADEC",
    "usdy": "#1B6AFF",
    "eurc": "#003399",
    "usdg": "#108FE7",
}


# ── Events ──────────────────────────────────────────────────────────────────

EVENT_COLORS: dict[str, str] = {
    "halving": "#F39C12",       # amber — Bitcoin halvings
    "fork": "#16A085",          # teal — protocol forks (London, Shapella, Cancun)
    "hack": "#C0392B",          # crimson — exploits / depegs
    "regulation": "#2C3E50",    # navy — SEC / FOMC / ETF approvals
    "launch": "#27AE60",        # green — TGE / mainnet / app launch
    "exchange": "#7F8C8D",      # gray — Mt Gox, FTX, Celsius collapse
    "vote": "#9C27B0",          # purple — governance vote / unlock
    "macro": "#34495E",         # slate — macro event / rate decision
}


# ── Aliases ─────────────────────────────────────────────────────────────────

# Lower-cased alias → canonical key. Token aliases default to the spot token.
_ALIASES: dict[str, str] = {
    # token aliases
    "bitcoin": "btc",
    "wbtc": "btc",
    "tbtc": "btc",
    "ethereum": "eth",
    "weth": "eth",
    "steth": "eth",
    "wsteth": "eth",
    "reth": "eth",
    "ether": "eth",
    "tether": "usdt",
    "usd-coin": "usdc",
    "usd_coin": "usdc",
    "wsol": "sol",
    "msol": "sol",
    "jitosol": "sol",
    "wbnb": "bnb",
    "wavax": "avax",
    "wmatic": "matic",
    "polygon": "matic",  # ambiguous — defaults to token; chain key 'polygon'
    "wpol": "pol",
    "ripple": "xrp",
    "dogecoin": "doge",
    "cardano-token": "ada",
    "tron-token": "trx",
    "chainlink": "link",
    "matic-token": "matic",
    "polkadot-token": "dot",
    "litecoin": "ltc",
    "bitcoin-cash": "bch",
    "toncoin": "ton",
    "cosmos-hub": "atom",
    "near-protocol": "near",
    "aptos-token": "apt",
    "sui-token": "sui",
    "arbitrum-token": "arb",
    "optimism-token": "op",
    "hyperliquid-token": "hype",
    "worldcoin": "wld",
    "bittensor": "tao",
    "kaspa": "kas",
    "render-token": "rndr",
    "injective": "inj",
    "internet-computer": "icp",
    "filecoin": "fil",
    "uniswap-token": "uni",
    "aave-token": "aave",
    "compound-token": "comp",
    "maker": "mkr",
    "curve-dao": "crv",
    "lido-dao": "ldo",
    "rocket-pool": "rpl",
    "balancer-token": "bal",
    "pendle-token": "pendle",
    "gmx-token": "gmx",
    "synthetix-network-token": "snx",
    "sushiswap-token": "sushi",
    "pancakeswap-token": "cake",
    "dydx-token": "dydx",
    "frax-share": "frax",
    "yearn-finance": "yfi",
    "convex-token": "cvx",
    "ethena-token": "ena",
    "ondo-token": "ondo",
    "render-network": "render",
    # chain aliases
    "eth-mainnet": "ethereum",
    "btc-mainnet": "bitcoin",
    "binance-smart-chain": "bnb",
    "binance-chain": "bnb",
    "avalanche-c": "avalanche",
    "ton-blockchain": "ton",
    "polygon-pos": "polygon",
    "matic-network": "polygon",
    "polygon-zk": "polygon-zkevm",
    "polygonzkevm": "polygon-zkevm",
    "zk-sync": "zksync",
    "zksync-era": "zksync",
    "starknet-l2": "starknet",
    "world-chain": "world",
    # protocol aliases
    "uni": "uniswap",
    "uniswap-v2": "uniswap",
    "uniswap-v3": "uniswap",
    "uniswap-v4": "uniswap",
    "maker-dao": "makerdao",
    "rocket-pool-token": "rocketpool",
    "rocketpool-protocol": "rocketpool",
    "1inch-network": "1inch",
    "yearn-protocol": "yearn",
    "convex-finance": "convex",
    "stargate-finance": "stargate",
    "across-protocol": "across",
    "hop-protocol": "hop",
    "ondo-finance": "ondo",
    "morpho-blue": "morpho",
    "etherfi-protocol": "etherfi",
    "ether-fi": "etherfi",
    "renzo-protocol": "renzo",
    "kelp-dao": "kelp",
    "marinade-finance": "marinade",
    "spark-protocol": "spark",
    "compound-protocol": "compound",
}


def _normalize(name: str) -> str:
    s = name.strip().lower()
    if s.startswith("$"):
        s = s[1:]
    s = s.replace("_", "-").replace(" ", "-")
    return _ALIASES.get(s, s)


def _dark_swap(hex_color: str) -> str:
    """Return a brightened variant of ``hex_color`` for dark backgrounds.

    Heuristic (matches the visual-signature research):
        * Warm hues (reds / oranges / yellows / red-purples) self-luminate
          on dark backgrounds — return unchanged.
        * Deep cool hues (blues, purples, greens) get an HSL lightness bump
          of ~10 percentage points (capped at 0.85), keeping the hue and
          saturation. Mirrors the research target ETH #627EEA → #88AAF1.
        * Already-very-light or near-gray colours are left alone.
    """
    import colorsys

    h_str = hex_color.lstrip("#")
    if len(h_str) != 6:
        return hex_color
    try:
        r, g, b = int(h_str[0:2], 16), int(h_str[2:4], 16), int(h_str[4:6], 16)
    except ValueError:
        return hex_color

    h_, l_, s_ = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    is_warm = h_ <= 0.12 or h_ >= 0.93
    is_already_light = l_ >= 0.80
    is_near_gray = s_ < 0.15

    if is_warm or is_already_light or is_near_gray:
        return hex_color

    l_new = min(l_ + 0.10, 0.82)
    r2, g2, b2 = colorsys.hls_to_rgb(h_, l_new, s_)
    return f"#{int(round(r2 * 255)):02X}{int(round(g2 * 255)):02X}{int(round(b2 * 255)):02X}"


# ── Public API ──────────────────────────────────────────────────────────────


def color_for(
    name: str,
    *,
    kind: str | None = None,
    mode: ThemeMode | None = None,
) -> str | None:
    """Resolve a brand name to its canonical hex.

    Args:
        name: free-form token / chain / protocol name. Case-insensitive,
            accepts aliases, ``$``-prefix, kebab/snake/space joining.
        kind: optional disambiguator. ``"token"``, ``"chain"``, ``"protocol"``,
            ``"stablecoin"``, ``"event"``. When ``None``, the resolver searches
            in that order — first match wins.
        mode: theme mode; defaults to the currently applied theme. Dark mode
            brightens deep cool hues automatically.

    Returns:
        A ``"#RRGGBB"`` string, or ``None`` if the name doesn't match any
        registered brand.
    """
    if not name or not isinstance(name, str):
        return None
    key = _normalize(name)
    table_order: list[dict[str, str]]
    if kind is None:
        table_order = [TOKEN_COLORS, CHAIN_COLORS, PROTOCOL_COLORS, STABLECOIN_COLORS, EVENT_COLORS]
    elif kind == "token":
        table_order = [TOKEN_COLORS]
    elif kind == "chain":
        table_order = [CHAIN_COLORS]
    elif kind == "protocol":
        table_order = [PROTOCOL_COLORS]
    elif kind == "stablecoin":
        table_order = [STABLECOIN_COLORS]
    elif kind == "event":
        table_order = [EVENT_COLORS]
    else:
        raise ValueError(
            f"Unknown kind: {kind!r}. Use one of: token, chain, protocol, "
            f"stablecoin, event."
        )

    for table in table_order:
        if key in table:
            base = table[key]
            return _dark_swap(base) if (mode or current_mode()) == ThemeMode.DARK else base
    return None


def is_brand_known(name: str) -> bool:
    """Return True if :func:`color_for` would return a hex for ``name``."""
    return color_for(name) is not None


def palette_for(names: list[str], *, mode: ThemeMode | None = None) -> list[str]:
    """Return a colour for every name, falling back to the categorical cycle.

    Stable: the same unknown name maps to the same cycle slot across calls,
    so re-rendering the chart doesn't shuffle colours.
    """
    cycle = list(OKABE_ITO_DARK if (mode or current_mode()) == ThemeMode.DARK else OKABE_ITO)
    out: list[str] = []
    for n in names:
        c = color_for(n, mode=mode)
        if c is not None:
            out.append(c)
        else:
            slot = abs(hash(_normalize(n))) % len(cycle)
            out.append(cycle[slot])
    return out
