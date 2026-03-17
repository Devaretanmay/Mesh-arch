"""Violation history tracking module."""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class CommitRecord:
    """Represents violations for a single commit."""

    commit_hash: str
    timestamp: str
    message: str
    violations_introduced: list[str] = field(default_factory=list)
    violations_fixed: list[str] = field(default_factory=list)
    net_delta: int = 0


class HistoryTracker:
    """Tracks violation history over commits."""

    def __init__(self, codebase_root: Path):
        """Initialize the history tracker.

        Args:
            codebase_root: Root directory of the codebase.
        """
        self.codebase_root = codebase_root.resolve()
        self.mesh_dir = self.codebase_root / ".mesh"
        self.history_file = self.mesh_dir / "history.json"
        self.records: list[CommitRecord] = []
        self._load_history()

    def _load_history(self) -> None:
        """Load history from file."""
        self.records = []

        if not self.history_file.exists():
            return

        try:
            content = self.history_file.read_text()
            data = json.loads(content)

            for record in data.get("commits", []):
                self.records.append(
                    CommitRecord(
                        commit_hash=record.get("commit_hash", ""),
                        timestamp=record.get("timestamp", ""),
                        message=record.get("message", ""),
                        violations_introduced=record.get("violations_introduced", []),
                        violations_fixed=record.get("violations_fixed", []),
                        net_delta=record.get("net_delta", 0),
                    )
                )

        except Exception:
            pass

    def _save_history(self) -> None:
        """Save history to file."""
        try:
            self.mesh_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "commits": [
                    {
                        "commit_hash": r.commit_hash,
                        "timestamp": r.timestamp,
                        "message": r.message,
                        "violations_introduced": r.violations_introduced,
                        "violations_fixed": r.violations_fixed,
                        "net_delta": r.net_delta,
                    }
                    for r in self.records
                ],
            }

            self.history_file.write_text(json.dumps(data, indent=2))

        except Exception:
            pass

    def record_commit(
        self,
        commit_hash: str,
        violations_before: list[str],
        violations_after: list[str],
    ) -> CommitRecord:
        """Record a commit's violation changes.

        Args:
            commit_hash: Git commit hash.
            violations_before: Violations before the commit.
            violations_after: Violations after the commit.

        Returns:
            CommitRecord for the commit.
        """
        introduced = set(violations_after) - set(violations_before)
        fixed = set(violations_before) - set(violations_after)

        message = self._get_commit_message(commit_hash)
        timestamp = self._get_commit_timestamp(commit_hash)

        record = CommitRecord(
            commit_hash=commit_hash,
            timestamp=timestamp,
            message=message,
            violations_introduced=list(introduced),
            violations_fixed=list(fixed),
            net_delta=len(introduced) - len(fixed),
        )

        self.records.append(record)

        while len(self.records) > 100:
            self.records.pop(0)

        self._save_history()

        return record

    def _get_commit_message(self, commit_hash: str) -> str:
        """Get commit message from git.

        Args:
            commit_hash: Git commit hash.

        Returns:
            Commit message string.
        """
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%s", commit_hash],
                cwd=self.codebase_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _get_commit_timestamp(self, commit_hash: str) -> str:
        """Get commit timestamp from git.

        Args:
            commit_hash: Git commit hash.

        Returns:
            Timestamp string.
        """
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ci", commit_hash],
                cwd=self.codebase_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return datetime.now().isoformat()

    def get_history(
        self, last_n: int = 20, file_filter: str | None = None
    ) -> list[CommitRecord]:
        """Get violation history.

        Args:
            last_n: Number of recent commits to return.
            file_filter: Optional file path to filter by.

        Returns:
            List of CommitRecord objects.
        """
        records = self.records[-last_n:] if last_n > 0 else self.records

        if file_filter:
            filtered = []
            for record in records:
                introduced = [
                    v for v in record.violations_introduced if file_filter in v
                ]
                fixed = [v for v in record.violations_fixed if file_filter in v]
                if introduced or fixed:
                    filtered.append(
                        CommitRecord(
                            commit_hash=record.commit_hash,
                            timestamp=record.timestamp,
                            message=record.message,
                            violations_introduced=introduced,
                            violations_fixed=fixed,
                            net_delta=len(introduced) - len(fixed),
                        )
                    )
            return filtered

        return records

    def get_summary(self) -> dict:
        """Get violation history summary.

        Returns:
            Dict with summary statistics.
        """
        if not self.records:
            return {
                "total_commits": 0,
                "total_introduced": 0,
                "total_fixed": 0,
                "current_violations": 0,
            }

        total_introduced = sum(len(r.violations_introduced) for r in self.records)
        total_fixed = sum(len(r.violations_fixed) for r in self.records)

        current_violations = 0
        if self.records:
            all_introduced = set()
            all_fixed = set()
            for r in self.records:
                all_introduced.update(r.violations_introduced)
                all_fixed.update(r.violations_fixed)
            current_violations = len(all_introduced - all_fixed)

        return {
            "total_commits": len(self.records),
            "total_introduced": total_introduced,
            "total_fixed": total_fixed,
            "current_violations": current_violations,
        }

    def format_history(self, last_n: int = 20, file_filter: str | None = None) -> str:
        """Format history as text table.

        Args:
            last_n: Number of commits to show.
            file_filter: Optional file path to filter by.

        Returns:
            Formatted text table.
        """
        records = self.get_history(last_n, file_filter)

        if not records:
            return "No violation history found."

        lines = []
        lines.append("━" * 70)
        lines.append("  Mesh Violation History")
        lines.append("━" * 70)
        lines.append("")
        lines.append(
            f"  {'Commit':<12} {'Introduced':>10} {'Fixed':>8} {'Net':>6}  Message"
        )
        lines.append("  " + "─" * 66)

        for record in records:
            short_hash = record.commit_hash[:8] if record.commit_hash else "unknown"
            introduced = len(record.violations_introduced)
            fixed = len(record.violations_fixed)
            net = record.net_delta
            net_str = f"+{net}" if net > 0 else str(net)
            message = record.message[:40] if record.message else ""

            lines.append(
                f"  {short_hash:<12} {introduced:>10} {fixed:>8} {net_str:>6}  {message}"
            )

        lines.append("")

        summary = self.get_summary()
        lines.append(
            f"  Total: {summary['total_commits']} commits, "
            f"{summary['total_introduced']} introduced, "
            f"{summary['total_fixed']} fixed, "
            f"{summary['current_violations']} current violations"
        )

        lines.append("━" * 70)

        return "\n".join(lines)
