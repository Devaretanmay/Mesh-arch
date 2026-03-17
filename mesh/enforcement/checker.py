"""Core violation checker for git diff-based analysis."""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mesh.analysis.builder import (
    AnalysisBuilder,
    detect_duplicates,
    detect_circular_calls,
    detect_naming_violations,
    detect_data_flow_violations,
)
from mesh.analysis.taint import detect_taint_violations
from mesh.core.storage import MeshStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Violation:
    """Represents a single code violation."""

    id: str
    kind: str
    severity: str
    message: str
    file_path: str
    line: int
    related_files: list[str] = field(default_factory=list)
    fix_hint: str = ""
    introduced_at: str | None = None


@dataclass
class CheckResult:
    """Result of a mesh check operation."""

    violations: list[Violation]
    files_checked: int
    duration_ms: float
    is_clean: bool
    commit_hash: str | None = None


class ViolationChecker:
    """Checks git diffs for code violations."""

    def __init__(self, codebase_root: Path):
        """Initialize the violation checker.

        Args:
            codebase_root: Root directory of the codebase.
        """
        self.codebase_root = codebase_root.resolve()
        self.mesh_dir = self.codebase_root / ".mesh"
        self.storage = MeshStorage(self.codebase_root)

    def check_staged(
        self,
        strict: bool = False,
        ignored_patterns: list[str] | None = None,
    ) -> CheckResult:
        """Check staged files for violations.

        Args:
            strict: If True, check entire codebase instead of just staged files.
            ignored_patterns: List of violation patterns to ignore.

        Returns:
            CheckResult with violations found.
        """
        start_time = time.time()

        try:
            if strict:
                files_to_check = self._get_all_python_files()
            else:
                files_to_check = self._get_staged_files()

            if not files_to_check:
                return CheckResult(
                    violations=[],
                    files_checked=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    is_clean=True,
                    commit_hash=self._get_current_commit(),
                )

            violations = self._check_files(files_to_check, ignored_patterns or [])

            return CheckResult(
                violations=violations,
                files_checked=len(files_to_check),
                duration_ms=(time.time() - start_time) * 1000,
                is_clean=len(violations) == 0,
                commit_hash=self._get_current_commit(),
            )

        except Exception as e:
            logger.exception("Checker crashed")
            self._log_error(e)
            return CheckResult(
                violations=[],
                files_checked=0,
                duration_ms=(time.time() - start_time) * 1000,
                is_clean=True,
                commit_hash=self._get_current_commit(),
            )

    def _get_staged_files(self) -> list[Path]:
        """Get list of staged Python files from git.

        Returns:
            List of staged .py and .ts files.
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                cwd=self.codebase_root,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"git diff failed: {result.stderr}")
                return []

            files = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    file_path = self.codebase_root / line
                    if file_path.exists() and file_path.suffix in (
                        ".py",
                        ".ts",
                        ".tsx",
                    ):
                        if ".mesh" not in str(file_path):
                            files.append(file_path)

            return files

        except subprocess.TimeoutExpired:
            logger.warning("git diff timed out")
            return []
        except Exception as e:
            logger.warning(f"Failed to get staged files: {e}")
            return []

    def _get_all_python_files(self) -> list[Path]:
        """Get all Python files in the codebase.

        Returns:
            List of all .py and .ts files.
        """
        py_files = list(self.codebase_root.rglob("*.py"))
        ts_files = list(self.codebase_root.rglob("*.ts"))
        tsx_files = list(self.codebase_root.rglob("*.tsx"))

        all_files = [
            f
            for f in py_files + ts_files + tsx_files
            if ".mesh" not in str(f) and f.exists()
        ]
        return all_files

    def _check_files(
        self,
        files: list[Path],
        ignored_patterns: list[str],
    ) -> list[Violation]:
        """Check files for violations.

        Args:
            files: List of files to check.
            ignored_patterns: Patterns to ignore.

        Returns:
            List of violations found.
        """
        violations = []

        try:
            storage = MeshStorage(self.codebase_root)

            try:
                call_graph = storage.load_call_graph()
            except Exception:
                builder = AnalysisBuilder(self.codebase_root)
                builder.run_full_analysis()
                builder.close()
                call_graph = storage.load_call_graph()

            duplicates = detect_duplicates(call_graph)
            for dup in duplicates:
                violation = self._duplicate_to_violation(dup, files)
                if violation and not self._is_ignored(violation, ignored_patterns):
                    violations.append(violation)

            circular_calls = detect_circular_calls(call_graph)
            for circ in circular_calls:
                violation = self._circular_to_violation(circ, files)
                if violation and not self._is_ignored(violation, ignored_patterns):
                    violations.append(violation)

            naming_violations = detect_naming_violations(call_graph)
            for naming in naming_violations:
                violation = self._naming_to_violation(naming, files)
                if violation and not self._is_ignored(violation, ignored_patterns):
                    violations.append(violation)

            # Data flow violations
            try:
                data_flow_graph = storage.load_data_flow_graph()
                data_violations = detect_data_flow_violations(
                    data_flow_graph,
                    codebase_root=self.codebase_root,
                )
                for dv in data_violations:
                    violation = self._dataflow_to_violation(dv, files)
                    if violation and not self._is_ignored(violation, ignored_patterns):
                        violations.append(violation)
            except Exception as e:
                logger.warning(f"Data flow analysis failed: {e}")

            # Taint tracking violations (security)
            try:
                taint_violations = detect_taint_violations(
                    call_graph,
                    data_flow_graph,
                    codebase_root=self.codebase_root,
                )
                for tv in taint_violations:
                    violation = self._taint_to_violation(tv, files)
                    if violation and not self._is_ignored(violation, ignored_patterns):
                        violations.append(violation)
            except Exception as e:
                logger.warning(f"Taint analysis failed: {e}")

            storage.close()

        except Exception as e:
            logger.exception("Error during file checking")
            self._log_error(e)

        return violations

    def _duplicate_to_violation(
        self,
        dup: dict[str, Any],
        files: list[Path],
    ) -> Violation | None:
        """Convert duplicate detection result to Violation.

        Args:
            dup: Duplicate detection result dict.
            files: Files being checked.

        Returns:
            Violation object or None if not applicable.
        """
        kind = dup.get("kind", "duplicate")

        if kind == "duplicate":
            message = dup.get("message", "")
            file_path = dup.get("file_path", "")
            line = dup.get("line", 1)
            related = dup.get("related_files", [])

            return Violation(
                id=f"duplicate:{dup.get('message', 'unknown')}",
                kind="duplicate",
                severity="error",
                message=message,
                file_path=file_path,
                line=line,
                related_files=related,
                fix_hint=dup.get("fix_hint", "Consolidate duplicate"),
                introduced_at=self._get_current_commit(),
            )

        return None

    def _circular_to_violation(
        self,
        circ: dict[str, Any],
        files: list[Path],
    ) -> Violation | None:
        """Convert circular detection result to Violation.

        Args:
            circ: Circular detection result dict.
            files: Files being checked.

        Returns:
            Violation object or None if not applicable.
        """
        files_list = circ.get("files", [])
        if not files_list:
            return None

        first_file = files_list[0]
        severity = circ.get("severity", "error")

        return Violation(
            id=circ.get("issue_id", f"circular:{first_file}"),
            kind="circular",
            severity=severity,
            message=f"Circular dependency: {' -> '.join(files_list[:3])}",
            file_path=first_file,
            line=1,
            related_files=files_list[1:],
            fix_hint="Break cycle by extracting shared code or using dependency injection",
            introduced_at=self._get_current_commit(),
        )

    def _naming_to_violation(
        self,
        naming: dict[str, Any],
        files: list[Path],
    ) -> Violation | None:
        """Convert naming detection result to Violation.

        Args:
            naming: Naming detection result dict.
            files: Files being checked.

        Returns:
            Violation object or None if not applicable.
        """
        message = naming.get("message", "")
        file_path = naming.get("file_path", "")
        line = naming.get("line", 1)

        return Violation(
            id=f"naming:{message}",
            kind="naming",
            severity="warning",
            message=message,
            file_path=file_path,
            line=line,
            related_files=[],
            fix_hint=naming.get("fix_hint", "Rename to follow naming conventions"),
            introduced_at=self._get_current_commit(),
        )

    def _dataflow_to_violation(
        self,
        dataflow: dict[str, Any],
        files: list[Path],
    ) -> Violation | None:
        """Convert data flow detection result to Violation.

        Args:
            dataflow: Data flow violation result dict.
            files: Files being checked.

        Returns:
            Violation object or None if not applicable.
        """
        kind = dataflow.get("kind", "dataflow")
        message = dataflow.get("message", "")
        file_path = dataflow.get("file_path", "")
        line = dataflow.get("line", 1)
        related = dataflow.get("related_files", [])
        severity = dataflow.get("severity", "warning")

        return Violation(
            id=f"dataflow:{kind}:{message[:50]}",
            kind=kind,
            severity=severity,
            message=message,
            file_path=file_path,
            line=line,
            related_files=related,
            fix_hint=dataflow.get("fix_hint", "Review data flow"),
            introduced_at=self._get_current_commit(),
        )

    def _taint_to_violation(
        self,
        taint: dict[str, Any],
        files: list[Path],
    ) -> Violation | None:
        """Convert taint detection result to Violation.

        Args:
            taint: Taint violation result dict.
            files: Files being checked.

        Returns:
            Violation object or None if not applicable.
        """
        kind = taint.get("kind", "taint")
        message = taint.get("message", "")
        file_path = taint.get("file_path", "")
        line = taint.get("line", 1)
        related = taint.get("related_files", [])
        severity = taint.get("severity", "error")

        return Violation(
            id=f"taint:{kind}:{message[:50]}",
            kind=kind,
            severity=severity,
            message=message,
            file_path=file_path,
            line=line,
            related_files=related,
            fix_hint=taint.get("fix_hint", "Sanitize data before use"),
            introduced_at=self._get_current_commit(),
        )

    def _is_ignored(self, violation: Violation, patterns: list[str]) -> bool:
        """Check if violation matches any ignore pattern.

        Args:
            violation: Violation to check.
            patterns: List of ignore patterns.

        Returns:
            True if violation should be ignored.
        """
        for pattern in patterns:
            if pattern.startswith("file:"):
                parts = pattern[5:].split(":", 1)
                if len(parts) == 2:
                    file_pattern, kind_pattern = parts
                    if file_pattern in violation.file_path:
                        if kind_pattern == "*" or kind_pattern in violation.id:
                            return True

            elif pattern.startswith("duplicate:"):
                if pattern[10:] in violation.id:
                    return True

            elif pattern.startswith("naming:"):
                if pattern[7:] == "*" or pattern[7:] in violation.id:
                    return True

            elif pattern.startswith("circular:"):
                if pattern[9:] == "*" or pattern[9:] in violation.id:
                    return True

            elif pattern.endswith(":*"):
                kind = pattern[:-2]
                if violation.kind == kind:
                    return True

        return False

    def _get_current_commit(self) -> str | None:
        """Get current git commit hash.

        Returns:
            Commit hash or None if not in git repo.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.codebase_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _log_error(self, error: Exception) -> None:
        """Log error to .mesh/errors.log.

        Args:
            error: Exception that occurred.
        """
        error_log = self.mesh_dir / "errors.log"

        try:
            error_log.parent.mkdir(parents=True, exist_ok=True)

            current_size = error_log.stat().st_size if error_log.exists() else 0
            if current_size > 10 * 1024 * 1024:
                backup = error_log.with_suffix(".log.1")
                if backup.exists():
                    backup.unlink()
                error_log.rename(backup)
                error_log = self.mesh_dir / "errors.log"

            with open(error_log, "a") as f:
                import traceback

                f.write(
                    f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {type(error).__name__}\n"
                )
                f.write(f"{error}\n")
                f.write(traceback.format_exc())
                f.write("\n")

        except Exception as e:
            logger.warning(f"Failed to write error log: {e}")
