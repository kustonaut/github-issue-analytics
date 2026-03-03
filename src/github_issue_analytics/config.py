"""YAML-based configuration loader for GitHub Issue Analytics.

Handles label taxonomy, tracking patterns, thresholds, org members, and bot lists.
All repo-specific settings are configurable via YAML — no hardcoded values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TrackingPattern:
    """A regex pattern for detecting linked work items in issue bodies."""

    name: str
    pattern: str
    _compiled: re.Pattern | None = field(default=None, repr=False, compare=False)

    @property
    def regex(self) -> re.Pattern:
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled


@dataclass
class Thresholds:
    """Metric thresholds for scoring and alerting."""

    target_fix_rate: float = 0.10
    target_median_age_days: int = 90
    stale_days: int = 30
    regression_penalty: int = 3
    max_acceptable_ttfr_days: int = 7
    high_reaction_threshold: int = 5
    high_comment_threshold: int = 10
    backlog_age_buckets: list[int] = field(
        default_factory=lambda: [7, 30, 90, 180, 365, 730, 1095]
    )


@dataclass
class Config:
    """Top-level configuration for GitHub Issue Analytics.

    Loaded from a YAML file. All label taxonomy, tracking patterns,
    thresholds, and member lists are fully configurable.
    """

    repo: str
    area_labels: dict[str, list[str]] = field(default_factory=dict)
    type_labels: dict[str, list[str]] = field(default_factory=dict)
    status_labels: dict[str, list[str]] = field(default_factory=dict)
    tracking_patterns: list[TrackingPattern] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)
    org_members: list[str] = field(default_factory=list)
    bots: list[str] = field(default_factory=list)
    output_dir: str = "output"
    cache_dir: str = ".gia_cache"

    # Reverse lookup caches (label string → category name)
    _area_lookup: dict[str, str] = field(default_factory=dict, repr=False)
    _type_lookup: dict[str, str] = field(default_factory=dict, repr=False)
    _status_lookup: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._build_lookups()

    def _build_lookups(self):
        """Build reverse lookup maps: label string → category name."""
        self._area_lookup = {}
        for area_name, labels in self.area_labels.items():
            for label in labels:
                self._area_lookup[label.lower()] = area_name

        self._type_lookup = {}
        for type_name, labels in self.type_labels.items():
            for label in labels:
                self._type_lookup[label.lower()] = type_name

        self._status_lookup = {}
        for status_name, labels in self.status_labels.items():
            for label in labels:
                self._status_lookup[label.lower()] = status_name

    def classify_area(self, labels: list[str]) -> str:
        """Return the area name for a list of issue labels, or 'Unknown'."""
        for label in labels:
            area = self._area_lookup.get(label.lower())
            if area:
                return area
        return "Unknown"

    def classify_type(self, labels: list[str]) -> str:
        """Return the type name for a list of issue labels, or 'unknown'."""
        for label in labels:
            issue_type = self._type_lookup.get(label.lower())
            if issue_type:
                return issue_type
        return "unknown"

    def classify_status(self, labels: list[str]) -> str:
        """Return the status name for a list of issue labels, or 'untriaged'."""
        for label in labels:
            status = self._status_lookup.get(label.lower())
            if status:
                return status
        return "untriaged"

    def has_tracking_id(self, text: str) -> tuple[bool, str | None]:
        """Check if text contains any configured tracking ID pattern.

        Returns (found, pattern_name).
        """
        if not text:
            return False, None
        for tp in self.tracking_patterns:
            if tp.regex.search(text):
                return True, tp.name
        return False, None

    def is_bot(self, username: str) -> bool:
        """Check if a username is a known bot."""
        if not username:
            return False
        return username.lower() in {b.lower() for b in self.bots} or username.endswith("[bot]")

    def is_org_member(self, username: str) -> bool:
        """Check if a username is a known org member."""
        if not username:
            return False
        return username.lower() in {m.lower() for m in self.org_members}

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return cls._from_dict(raw)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> Config:
        """Build a Config from a raw dictionary."""
        tracking = []
        for tp in raw.get("tracking_patterns", []):
            tracking.append(TrackingPattern(name=tp["name"], pattern=tp["pattern"]))

        thresholds_raw = raw.get("thresholds", {})
        thresholds = Thresholds(
            target_fix_rate=thresholds_raw.get("target_fix_rate", 0.10),
            target_median_age_days=thresholds_raw.get("target_median_age_days", 90),
            stale_days=thresholds_raw.get("stale_days", 30),
            regression_penalty=thresholds_raw.get("regression_penalty", 3),
            max_acceptable_ttfr_days=thresholds_raw.get("max_acceptable_ttfr_days", 7),
            high_reaction_threshold=thresholds_raw.get("high_reaction_threshold", 5),
            high_comment_threshold=thresholds_raw.get("high_comment_threshold", 10),
            backlog_age_buckets=thresholds_raw.get(
                "backlog_age_buckets", [7, 30, 90, 180, 365, 730, 1095]
            ),
        )

        return cls(
            repo=raw.get("repo", ""),
            area_labels=raw.get("area_labels", {}),
            type_labels=raw.get("type_labels", {}),
            status_labels=raw.get("status_labels", {}),
            tracking_patterns=tracking,
            thresholds=thresholds,
            org_members=raw.get("org_members", []),
            bots=raw.get("bots", []),
            output_dir=raw.get("output_dir", "output"),
            cache_dir=raw.get("cache_dir", ".gia_cache"),
        )

    @classmethod
    def default(cls, repo: str) -> Config:
        """Create a minimal default config for a repo (no custom labels)."""
        return cls(
            repo=repo,
            type_labels={
                "bug": ["bug"],
                "feature": ["enhancement", "feature request"],
                "question": ["question"],
                "regression": ["regression"],
                "documentation": ["documentation"],
            },
            status_labels={
                "triaged": ["triaged"],
                "in_progress": ["in progress"],
                "fixed": ["fix committed", "fixed"],
                "wont_fix": ["wontfix", "won't fix"],
            },
            bots=[
                "github-actions[bot]",
                "dependabot[bot]",
                "stale[bot]",
            ],
        )
