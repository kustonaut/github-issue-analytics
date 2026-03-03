"""GitHub Issue Analytics — Turn thousands of GitHub issues into actionable intelligence."""

from github_issue_analytics.config import Config
from github_issue_analytics.etl import GitHubETL
from github_issue_analytics.metrics import MetricsEngine, MetricsResult
from github_issue_analytics.analyzer import Analyzer

__version__ = "0.1.0"
__all__ = ["Analyzer", "Config", "GitHubETL", "MetricsEngine", "MetricsResult"]
