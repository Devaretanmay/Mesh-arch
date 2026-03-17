""".meshignore file handling module."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class IgnorePattern:
    """Represents a single ignore pattern."""

    pattern: str
    kind: str
    scope: str
    comment: str = ""
    added_at: str = ""


class Ignorer:
    """Manages .meshignore file for suppressing violations."""

    def __init__(self, codebase_root: Path):
        """Initialize the ignorer.

        Args:
            codebase_root: Root directory of the codebase.
        """
        self.codebase_root = codebase_root.resolve()
        self.ignore_file = self.codebase_root / ".meshignore"
        self.patterns: list[IgnorePattern] = []
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Load patterns from .meshignore file."""
        self.patterns = []

        if not self.ignore_file.exists():
            return

        try:
            content = self.ignore_file.read_text()
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                pattern = IgnorePattern(
                    pattern=line,
                    kind=self._parse_kind(line),
                    scope=self._parse_scope(line),
                    comment="",
                )
                self.patterns.append(pattern)

        except Exception:
            pass

    def _parse_kind(self, pattern: str) -> str:
        """Parse the kind from a pattern.

        Args:
            pattern: Pattern string.

        Returns:
            Kind string (duplicate, naming, circular, file).
        """
        if pattern.startswith("file:"):
            return "file"
        elif pattern.startswith("duplicate:"):
            return "duplicate"
        elif pattern.startswith("naming:"):
            return "naming"
        elif pattern.startswith("circular:"):
            return "circular"
        elif pattern.endswith(":*"):
            return pattern[:-2]
        return "unknown"

    def _parse_scope(self, pattern: str) -> str:
        """Parse the scope from a pattern.

        Args:
            pattern: Pattern string.

        Returns:
            Scope string.
        """
        if pattern.startswith("file:"):
            parts = pattern[5:].split(":", 1)
            if len(parts) == 2:
                return parts[1]
            return "*"
        elif ":" in pattern:
            parts = pattern.split(":", 1)
            if len(parts) == 2:
                return parts[1]
        return "*"

    def is_ignored(self, violation_id: str, file_path: str = "") -> bool:
        """Check if a violation should be ignored.

        Args:
            violation_id: ID of the violation.
            file_path: Optional file path for file-scoped ignores.

        Returns:
            True if violation should be ignored.
        """
        for pattern in self.patterns:
            if self._matches(violation_id, file_path, pattern):
                return True
        return False

    def _matches(
        self,
        violation_id: str,
        file_path: str,
        pattern: IgnorePattern,
    ) -> bool:
        """Check if a violation matches a pattern.

        Args:
            violation_id: ID of the violation.
            file_path: File path of the violation.
            pattern: Pattern to match against.

        Returns:
            True if violation matches pattern.
        """
        if pattern.kind == "file":
            parts = pattern.pattern[5:].split(":", 1)
            if len(parts) == 2:
                file_pattern, kind_pattern = parts
                # Handle wildcards in file pattern
                if "*" in file_pattern:
                    # Convert glob-like pattern to simple contains check
                    file_pattern = file_pattern.replace("*", "")
                    if file_pattern not in file_path:
                        return False
                else:
                    if file_pattern not in file_path:
                        return False

                # Check kind pattern
                if kind_pattern == "*":
                    return True
                # Handle both "naming" and "naming:*" formats
                if kind_pattern.endswith(":*"):
                    kind_pattern = kind_pattern[:-2]
                if kind_pattern in violation_id:
                    return True
            return False

        elif pattern.kind == "duplicate":
            target = pattern.pattern[10:]
            if target in violation_id:
                return True

        elif pattern.kind == "naming":
            target = pattern.pattern[7:]
            if target == "*":
                return violation_id.startswith("naming:")
            if target in violation_id:
                return True

        elif pattern.kind == "circular":
            target = pattern.pattern[9:]
            if target == "*":
                return violation_id.startswith("circular:")
            if target in violation_id:
                return True

        elif pattern.pattern.endswith(":*"):
            kind = pattern.pattern[:-2]
            if violation_id.startswith(kind):
                return True

        return False

    def add_ignore(self, violation_id: str, comment: str = "") -> dict:
        """Add a violation to the ignore list.

        Args:
            violation_id: ID of violation to ignore.
            comment: Optional comment explaining why.

        Returns:
            Dict with 'success' bool and 'message' str.
        """
        try:
            if not self.ignore_file.exists():
                self.ignore_file.write_text("# Mesh ignore file\n")

            content = self.ignore_file.read_text()
            lines = content.strip().split("\n")

            pattern_line = f"{violation_id}"
            if comment:
                timestamp = datetime.now().strftime("%Y-%m-%d")
                pattern_line = f"# Added: {timestamp} — {comment}\n{pattern_line}"

            if pattern_line not in content:
                lines.append("")
                if comment:
                    lines.append(
                        f"# Added: {datetime.now().strftime('%Y-%m-%d')} — {comment}"
                    )
                lines.append(violation_id)

            new_content = "\n".join(lines) + "\n"
            self.ignore_file.write_text(new_content)

            self._load_patterns()

            return {
                "success": True,
                "message": f"Added '{violation_id}' to .meshignore",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to add ignore: {e}",
            }

    def remove_ignore(self, pattern: str) -> dict:
        """Remove a pattern from the ignore list.

        Args:
            pattern: Pattern to remove.

        Returns:
            Dict with 'success' bool and 'message' str.
        """
        if not self.ignore_file.exists():
            return {
                "success": False,
                "message": "No .meshignore file found.",
            }

        try:
            content = self.ignore_file.read_text()
            lines = content.split("\n")

            new_lines = []
            removed = False
            skip_next_comment = False

            for i, line in enumerate(lines):
                stripped = line.strip()

                if stripped == pattern or pattern in stripped:
                    removed = True
                    if i > 0 and lines[i - 1].strip().startswith("#"):
                        skip_next_comment = True
                    continue

                if skip_next_comment and stripped.startswith("#"):
                    skip_next_comment = False
                    continue

                new_lines.append(line)

            if not removed:
                return {
                    "success": False,
                    "message": f"Pattern '{pattern}' not found.",
                }

            new_content = "\n".join(new_lines)
            self.ignore_file.write_text(new_content)

            self._load_patterns()

            return {
                "success": True,
                "message": f"Removed '{pattern}' from .meshignore",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to remove ignore: {e}",
            }

    def list_ignores(self) -> list[str]:
        """List all ignore patterns.

        Returns:
            List of pattern strings.
        """
        return [p.pattern for p in self.patterns]

    def validate_pattern(self, pattern: str) -> tuple[bool, str]:
        """Validate an ignore pattern.

        Args:
            pattern: Pattern to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not pattern:
            return False, "Pattern cannot be empty"

        valid_prefixes = ("duplicate:", "naming:", "circular:", "file:")
        if not any(pattern.startswith(p) for p in valid_prefixes):
            return False, f"Pattern must start with one of: {', '.join(valid_prefixes)}"

        if pattern.startswith("file:"):
            parts = pattern[5:].split(":", 1)
            if len(parts) != 2:
                return False, "File pattern must be in format: file:path/to/file:kind"
            # Allow both "naming" and "naming:*" formats, and just "*"
            kind_part = parts[1]
            if kind_part == "*":
                pass  # Valid - all kinds
            elif kind_part.endswith(":*"):
                # e.g., "naming:*"
                base_kind = kind_part[:-2]
                if base_kind not in ("duplicate", "naming", "circular"):
                    return (
                        False,
                        "File pattern kind must be *, or start with duplicate:/naming:/circular:",
                    )
            else:
                # e.g., "naming"
                if kind_part not in ("duplicate", "naming", "circular"):
                    return (
                        False,
                        "File pattern kind must be *, or be duplicate/naming/circular",
                    )
            return True, ""  # File pattern is valid

        if pattern.endswith(":*"):
            kind = pattern[:-2]
            if not any(kind.startswith(p) for p in ("duplicate", "naming", "circular")):
                return False, "Wildcard pattern must be for duplicate/naming/circular"

        return True, ""
