# centaur_charts

Matplotlib defaults, helpers, and chart routing for Centaur.

Every chart that ships through Centaur should flow through this package. The
goal is simple: a PNG that reads well on Slack mobile, with sane defaults
(sentence-case title, direct labels, brand-aware colours, 200-DPI export).

## Quickstart

```python
import centaur_charts as cc
import pandas as pd

cc.apply()                                   # install the Centaur theme
fig, ax = cc.subplots()                      # 16:9, 200 DPI on save

ax.plot(df.index, df["BTC"], label="BTC")
ax.plot(df.index, df["ETH"], label="ETH")
cc.highlight_one(ax, "ETH")                  # protagonist + greys
cc.direct_label_lines(ax)                    # no legend, end-of-line labels
cc.format_yaxis_dollars(ax)
cc.subtitle_title(ax,
    "ETH outperformed BTC by 38% YTD",
    subtitle="Indexed price, 1 Jan 2026 = 100")
cc.source_line(fig, "Source: CoinGecko · 30 Apr 2026")
cc.save(fig, "out.png")                      # closes the figure for you
```

Slack-mobile-readable defaults:

* `figsize = (8.0, 4.5)` × `dpi = 200` → 1600×900 PNG (lossless retina, fits
  Slack's mobile preview at ~360 px wide).
* Tick labels ≥ 9.5 pt at 200 DPI ≈ 21 px source — survives downsampling.
* No hover-only information — every fact reads from the inline image.

## Themes

```python
cc.apply()                # light editorial (default)
cc.apply(cc.ThemeMode.DARK)
cc.apply("editorial")     # off-white, serif-titled long-form
```

## What's in here

| Module | Role |
| ------ | ---- |
| `style` | rcParams + Okabe-Ito categorical palette |
| `helpers` | subplots, subtitle_title, source_line, direct_label_lines, highlight_one, with_focus, format_yaxis_*, annotate_recession, save |
| `styles/` | `.mplstyle` text files (light / dark / editorial) |
| `crypto/brand_colors` | Token / chain / protocol → hex resolver |
| `router` | `chart_router(intent, data) → ChartArtifact` |
| `handlers/` | One thin handler per chart type — line, bar, scatter, candle, treemap, ... |
