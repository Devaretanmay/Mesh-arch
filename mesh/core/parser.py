"""
UniversalParser — 25-language parser using ast-grep.

Parses any supported language into Mesh FunctionNodes.
Uses ast-grep-py from code-graph-mcp (Apache 2.0).

Language support:
  Python, TypeScript, JavaScript, Java, Go, Rust, C, C++, C#,
  Ruby, Kotlin, Swift, PHP, Dart, and more.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ast_grep_py import SgRoot

logger = logging.getLogger(__name__)


# Language → ast-grep language name mapping
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".cs": "c_sharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".dart": "dart",
    ".scala": "scala",
    ".vue": "vue",
    ".svelte": "svelte",
}

# Function definition node types per language
FUNCTION_NODES: dict[str, list[str]] = {
    "python": ["function_definition", "async_function_definition"],
    "typescript": [
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    ],
    "tsx": [
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    ],
    "javascript": [
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    ],
    "java": ["method_declaration", "constructor_declaration"],
    "go": ["function_declaration", "method_declaration"],
    "rust": ["function_item"],
    "kotlin": ["function_declaration"],
    "swift": ["function_declaration"],
    "c_sharp": ["method_declaration", "constructor_declaration"],
    "cpp": ["function_definition"],
    "c": ["function_definition"],
    "ruby": ["function", "def"],
    "php": ["function_definition", "method_declaration"],
    "dart": ["function_definition", "method_definition"],
}

# Call expression node types per language
CALL_NODES: dict[str, list[str]] = {
    "python": ["call"],
    "typescript": ["call_expression"],
    "tsx": ["call_expression"],
    "javascript": ["call_expression"],
    "java": ["method_invocation", "object_creation_expression"],
    "go": ["call_expression"],
    "rust": ["call_expression", "method_call_expression"],
    "kotlin": ["call_expression"],
    "swift": ["call_expression"],
    "c_sharp": ["invocation_expression"],
    "cpp": ["call_expression"],
    "c": ["call_expression"],
    "ruby": ["call", "send"],
    "php": ["call_expression"],
    "dart": ["method_invocation"],
}

# Class definition node types per language
CLASS_NODES: dict[str, list[str]] = {
    "python": ["class_definition"],
    "typescript": ["class_declaration", "class_expression"],
    "tsx": ["class_declaration", "class_expression"],
    "javascript": ["class_declaration", "class_expression"],
    "java": ["class_declaration", "interface_declaration", "enum_declaration"],
    "go": ["type_declaration"],
    "rust": ["struct_item", "impl_item", "enum_item"],
    "kotlin": ["class_declaration", "object_declaration"],
    "swift": ["class_declaration", "struct_declaration", "enum_declaration"],
    "c_sharp": ["class_declaration", "interface_declaration", "struct_declaration"],
    "cpp": ["class_specifier", "struct_specifier"],
    "dart": ["class_definition", "enum_definition"],
}


@dataclass
class ParsedFunction:
    """A parsed function from source code."""

    id: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str
    docstring: str
    calls: list[str] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    returns: list[str] = field(default_factory=list)
    kind: str = "function"
    data: dict = field(default_factory=dict)
    # Control flow fields
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    loops: list[dict] = field(default_factory=list)
    exception_handlers: list[dict] = field(default_factory=list)
    awaits: list[str] = field(default_factory=list)
    raises: list[str] = field(default_factory=list)


@dataclass
class ParsedClass:
    """A parsed class/type from source code."""

    id: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    kind: str = "class"
    data: dict = field(default_factory=dict)


class UniversalParser:
    """
    Parses any supported language into Mesh FunctionNodes.

    Uses ast-grep-py for parsing.
    Falls back gracefully for unsupported languages.
    """

    EXCLUDED_DIRS: set[str] = {
        "node_modules",
        "vendor",
        ".venv",
        "venv",
        "env",
        "site-packages",
        "dist",
        "build",
        "__pycache__",
        ".next",
        "out",
        "target",
        "bin",
        "obj",
        ".git",
        ".svn",
        "generated",
        "gen",
        ".idea",
        ".vscode",
        "migrations",
        "fixtures",
        "tests",
        ".pytest_cache",
        ".tox",
        ".eggs",
        "*.egg-info",
    }

    MAX_FILE_SIZE = 1024 * 1024  # 1MB max file size

    def __init__(self, root: Path | None = None):
        """
        Initialize parser.

        Args:
            root: Root directory for relative paths
        """
        self._root = root

    @property
    def root(self) -> Path | None:
        """Get root directory."""
        return self._root

    @root.setter
    def root(self, value: Path | None):
        """Set root directory."""
        self._root = value

    def get_language(self, file_path: Path) -> str | None:
        """Get ast-grep language for file extension."""
        return LANGUAGE_MAP.get(file_path.suffix.lower())

    def is_supported(self, file_path: Path) -> bool:
        """Check if file language is supported."""
        return self.get_language(file_path) is not None

    def should_skip(self, file_path: Path, root: Path) -> bool:
        """
        Check if file should be skipped.

        Args:
            file_path: File to check
            root: Root directory

        Returns:
            True if file should be skipped
        """
        try:
            relative = file_path.relative_to(root)
        except ValueError:
            return True

        # Check excluded directories
        parts = relative.parts
        for part in parts:
            if part in self.EXCLUDED_DIRS:
                return True

        # Check file size
        try:
            if file_path.stat().st_size > self.MAX_FILE_SIZE:
                return True
        except OSError:
            return True

        return False

    def parse_file(self, file_path: Path, root: Path) -> list[ParsedFunction]:
        """
        Parse file, return list of functions.

        Args:
            file_path: Path to file
            root: Root directory for relative paths

        Returns:
            List of ParsedFunction objects
        """
        # Check if should skip
        if self.should_skip(file_path, root):
            return []

        # Check if supported
        language = self.get_language(file_path)
        if language is None:
            return []

        # Read file
        try:
            code = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        return self.parse_code(code, str(file_path), language)

    def parse_code(
        self, code: str, file_path: str, language: str
    ) -> list[ParsedFunction]:
        """
        Parse code string into functions.

        Args:
            code: Source code
            file_path: File path for IDs
            language: ast-grep language name

        Returns:
            List of ParsedFunction objects
        """
        try:
            root = SgRoot(code, language)
        except Exception:
            return []

        func_kinds = FUNCTION_NODES.get(language, [])
        if not func_kinds:
            return []

        functions = []

        # Find all function definitions
        for kind in func_kinds:
            try:
                matches = root.root().find_all(kind=kind)
            except Exception:
                continue

            for match in matches:
                try:
                    func = self._extract_function(match, file_path, language, code)
                    if func:
                        functions.append(func)
                except Exception:
                    continue

        return functions

    def _extract_function(
        self,
        match: Any,
        file_path: str,
        language: str,
        source: str,
    ) -> ParsedFunction | None:
        """Extract function data from ast-grep match."""
        try:
            text = match.text()
            range_info = match.range()

            # Extract line numbers
            line_start = range_info.start.line if hasattr(range_info, "start") else 0
            line_end = range_info.end.line if hasattr(range_info, "end") else 0

            # Extract function name
            name = self._extract_name(match, language)
            if not name:
                return None

            # Generate stable ID
            func_id = self._make_function_id(file_path, name)

            # Extract signature (first line)
            lines = text.split("\n")
            signature = lines[0] if lines else text

            # Extract docstring (if present)
            docstring = self._extract_docstring(match, source)

            # Find calls within function
            calls = self._find_calls(match, language, source)

            # Extract params and returns (data flow)
            params, returns = self._extract_params_and_returns(match, source)

            # Extract control flow (Python only)
            is_async = False
            decorators = []
            branches = []
            loops = []
            exception_handlers = []
            awaits = []
            raises = []
            if language == "python":
                cf = self._extract_control_flow(match, source)
                is_async = cf.get("is_async", False)
                decorators = cf.get("decorators", [])
                branches = cf.get("branches", [])
                loops = cf.get("loops", [])
                exception_handlers = cf.get("exception_handlers", [])
                awaits = cf.get("awaits", [])
                raises = cf.get("raises", [])

            return ParsedFunction(
                id=func_id,
                name=name,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=signature,
                docstring=docstring,
                calls=calls,
                params=params,
                returns=returns,
                kind="function",
                is_async=is_async,
                decorators=decorators,
                branches=branches,
                loops=loops,
                exception_handlers=exception_handlers,
                awaits=awaits,
                raises=raises,
            )
        except Exception:
            return None

    def _extract_name(self, match: Any, language: str) -> str | None:
        """Extract function name from match."""
        try:
            # Try to get the name node
            if hasattr(match, "children"):
                for child in match.children():
                    if hasattr(child, "kind"):
                        kind = child.kind().lower()
                        if "identifier" in kind or "name" in kind:
                            return child.text()

            # Fallback: extract from text
            text = match.text()
            # For python: def func_name(...)
            if "def " in text:
                start = text.index("def ") + 4
                end = text.index("(", start)
                return text[start:end].strip()

            return None
        except Exception:
            return None

    def _extract_docstring(self, match: Any, source: str) -> str:
        """Extract docstring from function."""
        try:
            text = match.text()
            lines = text.split("\n")

            # Simple heuristic: first string literal after opening paren
            for i, line in enumerate(lines[1:], 1):
                line = line.strip()
                if line.startswith('"""') or line.startswith("'''"):
                    return line.strip("\"'")
                if line.startswith('"') or line.startswith("'"):
                    return line.strip("\"'")

            return ""
        except Exception:
            return ""

    def _find_calls(self, match: Any, language: str, source: str) -> list[str]:
        """Find function calls within function body."""
        call_kinds = CALL_NODES.get(language, [])
        calls = []

        for kind in call_kinds:
            try:
                sub_matches = match.find_all(kind=kind)
            except Exception:
                continue

            for sub in sub_matches:
                try:
                    name = self._extract_call_name(sub, language)
                    if name:
                        calls.append(name)
                except Exception:
                    continue

        return list(set(calls))  # Deduplicate

    def _extract_call_name(self, match: Any, language: str) -> str | None:
        """Extract function being called."""
        try:
            text = match.text()

            # Simple: get first identifier
            if "(" in text:
                name = text[: text.index("(")].strip()
                if name and name.isidentifier():
                    return name

            return text if text.isidentifier() else None
        except Exception:
            return None

    def _make_function_id(self, file_path: str, function_name: str) -> str:
        """
        Generate SHA256-based stable function ID.

        Format: sha256(rel_path:function_name)[:16]
        """
        content = f"{file_path}:{function_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _extract_params_and_returns(
        self, match: Any, source: str
    ) -> tuple[list[str], list[str]]:
        """Extract parameters and return values from function."""
        params = []
        returns = []

        try:
            text = match.text()

            # Extract parameters
            if "(" in text and ")" in text:
                paren_start = text.index("(")
                paren_end = text.index(")")
                params_str = text[paren_start + 1 : paren_end]
                for p in params_str.split(","):
                    p = p.strip().replace(",", "").split(":")[0].strip()
                    if p and p not in ("self", "cls"):
                        params.append(p)

            # Extract return values
            if "return " in text:
                for line in text.split("\n"):
                    if "return " in line:
                        ret = line.split("return ")[1].strip()
                        if ret and ret != "None":
                            ret_clean = ret.split(",")[0].strip()
                            if ret_clean not in returns:
                                returns.append(ret_clean)
        except Exception:
            pass

        return params, returns

    def _extract_control_flow(self, match: Any, source: str) -> dict[str, Any]:
        """
        Extract control flow information from function.

        Returns dict with:
        - is_async: bool
        - decorators: list[str]
        - branches: list[dict] - if/else branches
        - loops: list[dict] - for/while loops
        - exception_handlers: list[dict] - try/except
        - awaits: list[str] - awaited calls
        - raises: list[str] - raised exceptions
        """
        import ast

        result = {
            "is_async": False,
            "decorators": [],
            "branches": [],
            "loops": [],
            "exception_handlers": [],
            "awaits": [],
            "raises": [],
        }

        try:
            text = match.text()
            tree = ast.parse(text)
        except Exception:
            return result

        for node in ast.walk(tree):
            # Check for async function
            if isinstance(node, ast.AsyncFunctionDef):
                result["is_async"] = True

            # Extract decorators
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    dec_name = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
                    if not dec_name:
                        dec_name = getattr(decorator, "attr", None) or getattr(
                            decorator, "id", ""
                        )
                    if dec_name:
                        result["decorators"].append(dec_name)

            # Extract if/else branches
            if isinstance(node, ast.If):
                branch = {
                    "type": "if",
                    "line": node.lineno,
                    "condition": (
                        ast.unparse(node.test) if hasattr(ast, "unparse") else ""
                    ),
                }
                result["branches"].append(branch)

            # Extract loops
            if isinstance(node, (ast.For, ast.While)):
                loop = {
                    "type": "for" if isinstance(node, ast.For) else "while",
                    "line": node.lineno,
                }
                if isinstance(node, ast.For) and node.target:
                    loop["iterator"] = (
                        ast.unparse(node.target) if hasattr(ast, "unparse") else ""
                    )
                result["loops"].append(loop)

            # Extract try/except
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    exc_type = (
                        ast.unparse(handler.type)
                        if handler.type and hasattr(ast, "unparse")
                        else "Exception"
                    )
                    result["exception_handlers"].append(
                        {"type": exc_type, "line": handler.lineno}
                    )

            # Extract await expressions
            if isinstance(node, ast.Await):
                await_val = ast.unparse(node.value) if hasattr(ast, "unparse") else ""
                if await_val:
                    result["awaits"].append(await_val)

            # Extract raise statements
            if isinstance(node, ast.Raise):
                if node.exc:
                    exc = ast.unparse(node.exc) if hasattr(ast, "unparse") else ""
                    if exc:
                        result["raises"].append(exc)

        return result

    def parse_directory(self, root: Path) -> list[ParsedFunction]:
        """
        Parse all supported files in directory.

        Args:
            root: Root directory to parse

        Returns:
            List of all parsed functions
        """
        all_functions = []

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            funcs = self.parse_file(file_path, root)
            all_functions.extend(funcs)

        return all_functions

    def parse_classes_file(self, file_path: Path, root: Path) -> list[ParsedClass]:
        """
        Parse file for class/type definitions.

        Args:
            file_path: Path to file
            root: Root directory for relative paths

        Returns:
            List of ParsedClass objects
        """
        if self.should_skip(file_path, root):
            return []

        language = self.get_language(file_path)
        if language is None:
            return []

        try:
            code = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        return self.parse_classes_code(code, str(file_path), language)

    def parse_classes_code(
        self, code: str, file_path: str, language: str
    ) -> list[ParsedClass]:
        """Parse code string into classes."""
        try:
            root = SgRoot(code, language)
        except Exception:
            return []

        class_kinds = CLASS_NODES.get(language, [])
        if not class_kinds:
            return []

        classes = []

        for kind in class_kinds:
            try:
                matches = root.root().find_all(kind=kind)
            except Exception:
                continue

            for match in matches:
                try:
                    cls = self._extract_class(match, file_path, language, code)
                    if cls:
                        classes.append(cls)
                except Exception:
                    continue

        return classes

    def _extract_class(
        self,
        match: Any,
        file_path: str,
        language: str,
        source: str,
    ) -> ParsedClass | None:
        """Extract class data from ast-grep match."""
        try:
            range_info = match.range()

            line_start = range_info.start.line if hasattr(range_info, "start") else 0
            line_end = range_info.end.line if hasattr(range_info, "end") else 0

            name = self._extract_class_name(match, language)
            if not name:
                return None

            class_id = self._make_class_id(file_path, name)

            bases = self._extract_bases(match, language, source)
            methods = self._extract_methods(match, language, source)
            attributes = self._extract_attributes(match, language, source)

            return ParsedClass(
                id=class_id,
                name=name,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                bases=bases,
                methods=methods,
                attributes=attributes,
                kind="class",
            )
        except Exception:
            return None

    def _extract_class_name(self, match: Any, language: str) -> str | None:
        """Extract class name from match."""
        try:
            if hasattr(match, "children"):
                for child in match.children():
                    if hasattr(child, "kind"):
                        kind = child.kind().lower()
                        if "identifier" in kind or "name" in kind:
                            return child.text()

            text = match.text()
            if "class " in text:
                start = text.index("class ") + 6
                end = text.index("(", start) if "(" in text else len(text)
                return text[start:end].strip()

            return None
        except Exception:
            return None

    def _extract_bases(self, match: Any, language: str, source: str) -> list[str]:
        """Extract base classes/interfaces."""
        bases = []
        try:
            text = match.text()
            if "(" in text:
                paren_start = text.index("(")
                paren_end = text.index(")") if ")" in text else len(text)
                bases_str = text[paren_start + 1 : paren_end]
                for base in bases_str.split(","):
                    base = base.strip().replace(",", "")
                    if base and base != "object":
                        bases.append(base)
        except Exception:
            pass
        return bases

    def _extract_methods(self, match: Any, language: str, source: str) -> list[str]:
        """Extract method names from class body."""
        methods = []
        try:
            text = match.text()
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("def ") or line.startswith("async def "):
                    func_start = line.index("def ") + 4
                    if "async def " in line:
                        func_start = line.index("async def ") + 10
                    paren = line.index("(") if "(" in line else len(line)
                    name = line[func_start:paren].strip()
                    if name and not name.startswith("_"):
                        methods.append(name)
        except Exception:
            pass
        return methods

    def _extract_attributes(self, match: Any, language: str, source: str) -> list[str]:
        """Extract attribute assignments from class body."""
        attrs = []
        try:
            text = match.text()
            for line in text.split("\n"):
                line = line.strip()
                if ": " in line and "=" in line:
                    attr = line.split("=")[0].strip().replace(":", "").strip()
                    if attr and not attr.startswith("_"):
                        attrs.append(attr)
        except Exception:
            pass
        return attrs

    def _make_class_id(self, file_path: str, class_name: str) -> str:
        """Generate SHA256-based stable class ID."""
        content = f"{file_path}:{class_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def parse_classes_directory(self, root: Path) -> list[ParsedClass]:
        """Parse all supported files in directory for classes."""
        all_classes = []

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            classes = self.parse_classes_file(file_path, root)
            all_classes.extend(classes)

        return all_classes

    def parse_data_flow(
        self, file_path: Path, root: Path
    ) -> tuple[list[str], list[str]]:
        """
        Parse file for data flow (params and returns).

        Args:
            file_path: Path to file
            root: Root directory

        Returns:
            Tuple of (params, returns) lists
        """
        if self.should_skip(file_path, root):
            return [], []

        language = self.get_language(file_path)
        if language is None:
            return [], []

        try:
            code = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return [], []

        return self._extract_data_flow(code, language)

    def _extract_data_flow(
        self, code: str, language: str
    ) -> tuple[list[str], list[str]]:
        """Extract parameters and return values from code."""
        params = []
        returns = []

        try:
            root = SgRoot(code, language)
        except Exception:
            return [], []

        func_kinds = FUNCTION_NODES.get(language, [])

        for kind in func_kinds:
            try:
                matches = root.root().find_all(kind=kind)
            except Exception:
                continue

            for match in matches:
                try:
                    text = match.text()

                    if "(" in text:
                        paren_start = text.index("(")
                        paren_end = text.index(")") if ")" in text else len(text)
                        params_str = text[paren_start + 1 : paren_end]
                        for p in params_str.split(","):
                            p = p.strip().replace(",", "").split(":")[0].strip()
                            if p and p != "self" and p != "cls":
                                if p not in params:
                                    params.append(p)

                    if "return " in text:
                        for line in text.split("\n"):
                            if "return " in line:
                                ret = line.split("return ")[1].strip()
                                if ret and ret != "None":
                                    ret_clean = ret.split(",")[0].strip()
                                    if ret_clean not in returns:
                                        returns.append(ret_clean)
                except Exception:
                    continue

        return params, returns
