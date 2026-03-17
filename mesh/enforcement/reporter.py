"""Reporter module for formatting violation reports."""

import json
from pathlib import Path

from mesh.enforcement.checker import CheckResult, Violation


class Reporter:
    """Formats violation reports for CLI output."""

    def __init__(self, result: CheckResult):
        """Initialize the reporter.

        Args:
            result: CheckResult from violation checker.
        """
        self.result = result

    def format_text(self) -> str:
        """Format violations as human-readable text.

        Returns:
            Formatted text report.
        """
        lines = []

        if self.result.is_clean:
            lines.append("✅ Mesh: all checks passed")
            return "\n".join(lines)

        lines.append("━" * 50)
        lines.append(
            f"  Mesh blocked this commit — {len(self.result.violations)} violation(s) found"
        )
        lines.append("━" * 50)
        lines.append("")

        for violation in self.result.violations:
            icon = self._get_icon(violation.severity)
            lines.append(f"  {icon} [{violation.id}] {violation.kind.upper()}")

            file_line = f"{violation.file_path}:{violation.line}"
            lines.append(f"     {file_line}")

            lines.append(f"     {violation.message}")

            if violation.fix_hint:
                lines.append(f"     Fix: {violation.fix_hint}")

            lines.append(f"     Suppress: mesh ignore {violation.id}")
            lines.append("")

        lines.append("━" * 50)
        lines.append("  Run 'mesh explain <id>' for detailed guidance")
        lines.append("━" * 50)

        return "\n".join(lines)

    def format_json(self) -> str:
        """Format violations as JSON.

        Returns:
            JSON string with violation data.
        """
        data = {
            "files_checked": self.result.files_checked,
            "duration_ms": self.result.duration_ms,
            "is_clean": self.result.is_clean,
            "commit_hash": self.result.commit_hash,
            "violations": [
                {
                    "id": v.id,
                    "kind": v.kind,
                    "severity": v.severity,
                    "message": v.message,
                    "file_path": v.file_path,
                    "line": v.line,
                    "related_files": v.related_files,
                    "fix_hint": v.fix_hint,
                    "introduced_at": v.introduced_at,
                }
                for v in self.result.violations
            ],
        }
        return json.dumps(data, indent=2)

    def format_explain(
        self, violation_id: str, storage_path: Path | None = None
    ) -> str:
        """Format detailed explanation for a specific violation.

        Args:
            violation_id: ID of violation to explain.
            storage_path: Optional path to mesh storage for additional context.

        Returns:
            Detailed explanation text.
        """
        violation = None
        for v in self.result.violations:
            if v.id == violation_id:
                violation = v
                break

        if not violation:
            return f"Violation '{violation_id}' not found in current check results."

        lines = []
        lines.append("━" * 50)
        lines.append(f"  Explaining: {violation_id}")
        lines.append("━" * 50)
        lines.append("")

        lines.append("  WHAT IS THE PROBLEM")
        lines.append(f"  {violation.message}")
        lines.append(f"  Location: {violation.file_path}:{violation.line}")
        if violation.related_files:
            lines.append(f"  Related files: {', '.join(violation.related_files)}")
        lines.append("")

        lines.append("  WHY IT MATTERS")
        why = self._get_why(violation.kind)
        lines.append(f"  {why}")
        lines.append("")

        lines.append("  HOW TO FIX IT")
        fix = self._get_fix(violation)
        lines.append(f"  {fix}")
        lines.append("")

        lines.append("  TO SUPPRESS THIS WARNING (use sparingly)")
        lines.append(f"  mesh ignore {violation.id}")
        lines.append("━" * 50)

        return "\n".join(lines)

    def _get_icon(self, severity: str) -> str:
        """Get icon for severity level.

        Args:
            severity: 'error' or 'warning'.

        Returns:
            Icon emoji.
        """
        if severity == "error":
            return "🔴"
        elif severity == "warning":
            return "🟡"
        return "⚪"

    def _get_why(self, kind: str) -> str:
        """Get explanation of why this violation matters.

        Args:
            kind: Type of violation.

        Returns:
            Explanation string.
        """
        explanations = {
            "duplicate": (
                "Two implementations of the same function will diverge over time. "
                "Bug fixes applied to one will not reach the other. Future developers "
                "will not know which version is canonical."
            ),
            "circular": (
                "Circular dependencies make code harder to test and maintain. "
                "They prevent clean module boundaries and can cause import errors. "
                "Changes in one module may unexpectedly affect the other."
            ),
            "naming": (
                "Inconsistent naming makes code harder to read and understand. "
                "Developers expect certain naming patterns based on the project convention. "
                "Violations increase cognitive load during code review."
            ),
        }
        return explanations.get(
            kind, "This violation reduces code quality and maintainability."
        )

    def _get_fix(self, violation: Violation) -> str:
        """Get detailed fix guidance for a violation.

        Args:
            violation: Violation to explain.

        Returns:
            Fix guidance string.
        """
        if violation.kind == "duplicate":
            name = violation.id.replace("duplicate:", "")
            return (
                f"Option A (recommended): Find the original {name}() function and use it. "
                f"Delete the duplicate version in {violation.file_path}.\n\n"
                f"Option B: If this version intentionally replaces the old one, "
                f"delete the original and update all callers."
            )
        elif violation.kind == "circular":
            return (
                "Break the cycle by:\n"
                "  1. Extracting shared code to a third module\n"
                "  2. Using dependency injection\n"
                "  3. Merging the circular modules into one"
            )
        elif violation.kind == "naming":
            expected = violation.fix_hint.replace("Rename to ", "")
            return f"Rename {violation.id.replace('naming:', '')} to {expected} to match the project convention."
        else:
            return violation.fix_hint or "Review and fix the violation."
