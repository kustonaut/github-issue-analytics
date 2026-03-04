"""GitHub Issue Analytics — Turn thousands of GitHub issues into actionable intelligence."""

from github_issue_analytics.config import Config
from github_issue_analytics.etl import GitHubETL
from github_issue_analytics.funnel import generate_funnel, save_funnel
from github_issue_analytics.heatmap import generate_heatmap, save_heatmap
from github_issue_analytics.metrics import MetricsEngine, MetricsResult
from github_issue_analytics.analyzer import Analyzer

__version__ = "0.2.0"
__all__ = [
    "Analyzer",
    "Config",
    "GitHubETL",
    "MetricsEngine",
    "MetricsResult",
    "generate_funnel",
    "generate_heatmap",
    "save_funnel",
    "save_heatmap",
]
