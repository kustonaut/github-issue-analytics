"""Issue lifecycle funnel visualisation (matplotlib).

Renders a funnel chart showing how issues flow through lifecycle stages:

    INTAKE  →  TRIAGE  →  INVESTIGATE  →  CLOSE

Each stage is a horizontal bar whose width is proportional to the volume
at that stage.  Colour encodes health (green → amber → red).

Derived from the Brain OS KTWR funnel pattern (4 stages), adapted to
use MetricsResult data.

Usage::

    from github_issue_analytics.funnel import generate_funnel
    generate_funnel(metrics, "funnel.png")
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_issue_analytics.metrics import MetricsResult

# ── Colour palette (GitHub dark-theme aligned) ─────────────────────
_GREEN = "#3fb950"
_AMBER = "#d29922"
_RED = "#f85149"
_BG = "#0d1117"
_SURFACE = "#161b22"
_BORDER = "#30363d"
_TEXT = "#c9d1d9"
_TEXT_MUTED = "#8b949e"
_ACCENT = "#58a6ff"


@dataclass
class FunnelStage:
    """One horizontal bar in the funnel."""

    label: str
    value: int
    sublabel: str  # metric detail beneath the bar
    color: str  # hex colour


def _build_stages(metrics: "MetricsResult") -> list[FunnelStage]:
    """Map MetricsResult fields to the 4-stage funnel.

    Stages:
        1. INTAKE   — total open issues (backlog.total)
        2. TRIAGE   — issues not yet triaged (ttc_untriaged_count)
        3. ACTIVE   — issues being investigated (approx: open − untriaged)
        4. CLOSING  — recently closed issues (total_closed_recent)

    Colour logic:
        INTAKE:  RED if >1000, AMBER if >300, GREEN otherwise
        TRIAGE:  RED if untriaged% >40%, AMBER if >20%, GREEN
        ACTIVE:  always ACCENT (informational)
        CLOSING: GREEN if fix_rate >.50, AMBER if >.25, RED
    """
    total = metrics.backlog.total or metrics.total_open
    untriaged = metrics.ttc_untriaged_count
    active = max(0, total - untriaged)
    closed = metrics.total_closed_recent

    # INTAKE colour
    if total >= 1000:
        intake_color = _RED
    elif total >= 300:
        intake_color = _AMBER
    else:
        intake_color = _GREEN

    # TRIAGE colour
    untriaged_pct = metrics.ttc_untriaged_pct
    if untriaged_pct >= 40:
        triage_color = _RED
    elif untriaged_pct >= 20:
        triage_color = _AMBER
    else:
        triage_color = _GREEN

    # ACTIVE colour — neutral accent
    active_color = _ACCENT

    # CLOSING colour
    fr = metrics.fix_rate
    if fr >= 0.50:
        close_color = _GREEN
    elif fr >= 0.25:
        close_color = _AMBER
    else:
        close_color = _RED

    return [
        FunnelStage(
            label="INTAKE",
            value=total,
            sublabel=f"{total:,} open issues",
            color=intake_color,
        ),
        FunnelStage(
            label="TRIAGE",
            value=untriaged,
            sublabel=f"{untriaged:,} untriaged ({untriaged_pct:.1f}%)",
            color=triage_color,
        ),
        FunnelStage(
            label="ACTIVE",
            value=active,
            sublabel=f"{active:,} in investigation",
            color=active_color,
        ),
        FunnelStage(
            label="CLOSING",
            value=closed,
            sublabel=f"{closed:,} recently closed · fix rate {fr:.1%}",
            color=close_color,
        ),
    ]


def generate_funnel(
    metrics: "MetricsResult",
    output_path: str | Path | None = None,
    *,
    figsize: tuple[float, float] = (10, 5),
    dpi: int = 150,
    title: str | None = None,
) -> str | None:
    """Generate an issue lifecycle funnel chart.

    Args:
        metrics: Computed MetricsResult.
        output_path: Save path (PNG/SVG/PDF). ``None`` returns base64 PNG.
        figsize: Matplotlib figure size.
        dpi: Output resolution.
        title: Chart title; falls back to repo name.

    Returns:
        Absolute path of saved file, or base64 PNG string.
    """
    plt = importlib.import_module("matplotlib.pyplot")

    stages = _build_stages(metrics)
    max_value = max(s.value for s in stages) or 1
    n = len(stages)

    fig, ax = plt.subplots(figsize=figsize, facecolor=_BG)
    ax.set_facecolor(_BG)

    bar_height = 0.65
    y_positions = list(range(n - 1, -1, -1))  # top-down

    for idx, (stage, y) in enumerate(zip(stages, y_positions)):
        # Width proportional to max; minimum 8% so labels always visible
        width = max(stage.value / max_value, 0.08)

        # Centre bars to create funnel taper
        left = (1.0 - width) / 2.0

        ax.barh(
            y,
            width,
            left=left,
            height=bar_height,
            color=stage.color,
            edgecolor=_BORDER,
            linewidth=1,
            alpha=0.92,
            zorder=2,
        )

        # Stage label (centred on bar)
        ax.text(
            0.5,
            y + 0.05,
            f"{stage.label}",
            ha="center",
            va="center",
            fontsize=13,
            fontweight="bold",
            color="#ffffff",
            zorder=3,
        )

        # Value label (right of bar)
        ax.text(
            left + width + 0.02,
            y + 0.05,
            f"{stage.value:,}",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
            color=_TEXT,
            zorder=3,
        )

        # Sublabel (below bar)
        ax.text(
            0.5,
            y - 0.35,
            stage.sublabel,
            ha="center",
            va="center",
            fontsize=8,
            color=_TEXT_MUTED,
            zorder=3,
        )

        # Connector arrow between stages
        if idx < n - 1:
            ax.annotate(
                "",
                xy=(0.5, y - 0.42),
                xytext=(0.5, y - 0.58),
                arrowprops=dict(
                    arrowstyle="->",
                    color=_TEXT_MUTED,
                    lw=1.5,
                ),
                zorder=1,
            )

    # Axis cleanup
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.8, n - 1 + 0.8)
    ax.axis("off")

    # Title
    chart_title = title or f"Issue Lifecycle Funnel — {metrics.repo}"
    ax.set_title(
        chart_title,
        fontsize=14,
        fontweight="bold",
        color=_TEXT,
        pad=16,
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


def save_funnel(
    metrics: "MetricsResult",
    output_path: str | Path,
    **kwargs,
) -> str:
    """Convenience wrapper — always saves to disk.

    Returns:
        Absolute path of the saved image.
    """
    result = generate_funnel(metrics, output_path, **kwargs)
    if result is None:
        raise ValueError("Cannot generate funnel — no metrics data.")
    return result
