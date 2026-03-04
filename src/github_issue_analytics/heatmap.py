"""Product area × metric heatmap generator (matplotlib).

Renders a heat-grid PNG/SVG where rows are product areas and columns
are key health dimensions.  Colour encodes severity:
  GREEN (#3fb950)  → healthy
  AMBER (#d29922)  → moderate risk
  RED   (#f85149)  → critical concern

Each cell shows its raw value.  Works with zero external templates —
one function call produces a publication-ready image.

Usage::

    from github_issue_analytics.heatmap import generate_heatmap
    generate_heatmap(metrics, "heatmap.png")
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_issue_analytics.metrics import MetricsResult

import importlib

# ── Colour palette (GitHub dark-theme aligned) ─────────────────────
_GREEN = "#3fb950"
_AMBER = "#d29922"
_RED = "#f85149"
_BG = "#0d1117"
_SURFACE = "#161b22"
_BORDER = "#30363d"
_TEXT = "#c9d1d9"
_TEXT_MUTED = "#8b949e"

# ── Column definitions ─────────────────────────────────────────────
# Each column maps to a lambda that extracts a float from AreaMetrics
# plus thresholds for GREEN/AMBER/RED boundaries.
#   (label, extractor, green_below, red_above, fmt, higher_is_better)

_COLUMNS = [
    (
        "Total",
        lambda a: a.total,
        50,
        200,
        "{:.0f}",
        False,
    ),
    (
        "Bugs",
        lambda a: a.bugs,
        20,
        80,
        "{:.0f}",
        False,
    ),
    (
        "Regressions",
        lambda a: a.regressions,
        2,
        10,
        "{:.0f}",
        False,
    ),
    (
        "Med. Age (d)",
        lambda a: a.age.median,
        30,
        180,
        "{:.0f}",
        False,
    ),
    (
        "Fix Rate",
        lambda a: a.fix_rate * 100,  # convert to %
        None,  # filled dynamically (higher=better inversion)
        None,
        "{:.1f}%",
        True,
    ),
    (
        "Stale",
        lambda a: a.stale,
        5,
        30,
        "{:.0f}",
        False,
    ),
    (
        "DSAT",
        lambda a: a.dsat_score,
        30,
        100,
        "{:.0f}",
        False,
    ),
]


def _severity_color(
    value: float,
    green_below: float | None,
    red_above: float | None,
    higher_is_better: bool,
) -> str:
    """Return hex colour for a cell value given thresholds."""
    if higher_is_better:
        # Invert: high value = green, low value = red
        if green_below is None:
            # Fix Rate: >60% green, <30% red
            if value >= 60:
                return _GREEN
            if value <= 30:
                return _RED
            return _AMBER
        # Generic higher-is-better with explicit thresholds
        if value >= red_above:  # type: ignore[arg-type]
            return _GREEN
        if value <= green_below:
            return _RED
        return _AMBER
    else:
        # Normal: low value = green, high value = red
        if green_below is not None and value <= green_below:
            return _GREEN
        if red_above is not None and value >= red_above:
            return _RED
        return _AMBER


def _norm(
    value: float,
    green_below: float | None,
    red_above: float | None,
    higher_is_better: bool,
) -> float:
    """Normalise value to 0-1 for colour-mapping (0=green, 1=red)."""
    if higher_is_better:
        lo, hi = 30.0, 60.0
        if green_below is not None and red_above is not None:
            lo, hi = float(green_below), float(red_above)
        clamped = max(lo, min(hi, value))
        return 1.0 - (clamped - lo) / (hi - lo) if hi != lo else 0.5
    else:
        lo = float(green_below) if green_below is not None else 0.0
        hi = float(red_above) if red_above is not None else 100.0
        clamped = max(lo, min(hi, value))
        return (clamped - lo) / (hi - lo) if hi != lo else 0.5


def generate_heatmap(
    metrics: "MetricsResult",
    output_path: str | Path | None = None,
    *,
    figsize: tuple[float, float] | None = None,
    dpi: int = 150,
    title: str | None = None,
) -> str | None:
    """Generate a product-area × metric heatmap image.

    Args:
        metrics: Computed MetricsResult with per_area data.
        output_path: Where to save (PNG/SVG/PDF). ``None`` → returns raw
            bytes as base64-encoded PNG string.
        figsize: Matplotlib figure size. Auto-calculated if omitted.
        dpi: Output resolution (default 150).
        title: Chart title. Falls back to repo name.

    Returns:
        Absolute path of the saved file, or base64 PNG string if no
        output_path was given.
    """
    plt = importlib.import_module("matplotlib.pyplot")
    mcolors = importlib.import_module("matplotlib.colors")

    areas = metrics.per_area
    if not areas:
        return None

    n_rows = len(areas)
    n_cols = len(_COLUMNS)

    if figsize is None:
        figsize = (max(8, n_cols * 1.6), max(3, n_rows * 0.55 + 1.5))

    # ── Build data grid ────────────────────────────────────────────
    values: list[list[float]] = []
    norms: list[list[float]] = []
    labels: list[list[str]] = []

    for area in areas:
        row_vals: list[float] = []
        row_norms: list[float] = []
        row_labels: list[str] = []
        for _, extractor, g, r, fmt, hib in _COLUMNS:
            v = extractor(area)
            row_vals.append(v)
            row_norms.append(_norm(v, g, r, hib))
            row_labels.append(fmt.format(v))
        values.append(row_vals)
        norms.append(row_norms)
        labels.append(row_labels)

    # ── Render ─────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize, facecolor=_BG)
    ax.set_facecolor(_SURFACE)

    # Custom colourmap: green → amber → red
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "gia_heatmap",
        [_GREEN, _AMBER, _RED],
        N=256,
    )

    import numpy as np

    data = np.array(norms)
    im = ax.imshow(data, cmap=cmap, aspect="auto", vmin=0, vmax=1)

    # Axis labels
    area_names = [a.area[:28] for a in areas]  # truncate long names
    col_names = [c[0] for c in _COLUMNS]

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(col_names, fontsize=9, color=_TEXT, rotation=30, ha="right")
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(area_names, fontsize=9, color=_TEXT)

    # Cell text annotations
    for i in range(n_rows):
        for j in range(n_cols):
            # Choose text colour for contrast
            bg_norm = norms[i][j]
            txt_color = "#ffffff" if bg_norm > 0.55 else "#000000"
            ax.text(
                j,
                i,
                labels[i][j],
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color=txt_color,
            )

    # Grid lines
    ax.set_xticks([x - 0.5 for x in range(1, n_cols)], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, n_rows)], minor=True)
    ax.grid(which="minor", color=_BORDER, linewidth=0.5)
    ax.tick_params(which="minor", length=0)

    # Title
    chart_title = title or f"Area Health Heatmap — {metrics.repo}"
    ax.set_title(
        chart_title,
        fontsize=13,
        fontweight="bold",
        color=_TEXT,
        pad=14,
    )

    fig.tight_layout()

    # ── Save / return ──────────────────────────────────────────────
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), dpi=dpi, facecolor=_BG, bbox_inches="tight")
        plt.close(fig)
        return str(out.resolve())
    else:
        import base64
        import io

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, facecolor=_BG, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("ascii")


def save_heatmap(
    metrics: "MetricsResult",
    output_path: str | Path,
    **kwargs,
) -> str:
    """Convenience wrapper — always saves to disk.

    Returns:
        Absolute path of the saved image.
    """
    result = generate_heatmap(metrics, output_path, **kwargs)
    if result is None:
        raise ValueError("No per_area data — cannot generate heatmap.")
    return result
