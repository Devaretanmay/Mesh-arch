"""
UniversalParser — High-performance 25-language parser using ast-grep.

Optimizations:
- Parallel file processing with ThreadPoolExecutor
- Single-pass parsing (functions + classes together)
- Batch processing with progress callbacks
- Comprehensive file filtering
- Memory-efficient processing
- Error resilience

Language support:
  Python, TypeScript, JavaScript, Java, Go, Rust, C, C++, C#,
  Ruby, Kotlin, Swift, PHP, Dart, and more.
"""

from __future__ import annotations

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ast_grep_py import SgRoot

logger = logging.getLogger(__name__)


LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "typescript",
    ".jsx": "tsx",
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
    ".lua": "lua",
    ".pl": "perl",
    ".r": "r",
    ".scala": "scala",
}

FUNCTION_NODES: dict[str, list[str]] = {
    "python": ["function_definition", "async_function_definition"],
    "typescript": ["function_declaration", "method_definition", "arrow_function", "function_expression"],
    "tsx": ["function_declaration", "method_definition", "arrow_function", "function_expression"],
    "javascript": ["function_declaration", "method_definition", "arrow_function", "function_expression"],
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
    "lua": ["function_declaration"],
    "perl": ["subroutine_declaration"],
    "r": ["function_definition"],
    "scala": ["function_definition", "class_definition"],
}

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
    "lua": ["function_call"],
    "perl": ["function_call"],
    "r": ["function_call"],
    "scala": ["method_invocation"],
}

CLASS_NODES: dict[str, list[str]] = {
    "python": ["class_definition"],
    "typescript": ["class_declaration", "class_expression", "interface_declaration"],
    "tsx": ["class_declaration", "class_expression"],
    "javascript": ["class_declaration", "class_expression", "interface_declaration"],
    "java": ["class_declaration", "interface_declaration", "enum_declaration"],
    "go": ["type_declaration"],
    "rust": ["struct_item", "impl_item", "enum_item"],
    "kotlin": ["class_declaration", "object_declaration"],
    "swift": ["class_declaration", "struct_declaration", "enum_declaration"],
    "c_sharp": ["class_declaration", "interface_declaration", "struct_declaration"],
    "cpp": ["class_specifier", "struct_specifier"],
    "dart": ["class_definition", "enum_definition"],
    "lua": ["function_declaration"],
    "perl": ["class_declaration"],
    "r": ["class_definition"],
    "scala": ["class_definition", "object_definition", "trait_definition"],
}

IMPORT_NODES: dict[str, list[str]] = {
    "python": ["import_statement", "import_from_statement"],
    "typescript": ["import_statement", "import_clause"],
    "tsx": ["import_statement", "import_clause"],
    "javascript": ["import_statement", "import_clause"],
    "java": ["import_declaration"],
    "go": ["import_declaration"],
    "rust": ["use_declaration"],
    "kotlin": ["import_directive"],
    "swift": ["import_declaration"],
    "c_sharp": ["using_directive"],
    "cpp": ["using_declaration", "include_statement"],
    "c": ["include_statement"],
    "ruby": ["require_statement", "require_relative"],
    "php": ["use_declaration", "require_once_statement"],
    "dart": ["import_directive"],
    "lua": ["require"],
    "perl": ["use_statement", "require_statement"],
    "r": ["library_statement", "require_statement"],
    "scala": ["import_statement"],
}


@dataclass
class ParsedFunction:
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
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    loops: list[dict] = field(default_factory=list)
    exception_handlers: list[dict] = field(default_factory=list)
    awaits: list[str] = field(default_factory=list)
    raises: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class ParsedClass:
    id: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    kind: str = "class"


@dataclass
class ParseResult:
    functions: list[ParsedFunction]
    classes: list[ParsedClass]
    errors: list[str]


@dataclass
class FileHash:
    path: str
    mtime: float
    size: int
    hash: str


class UniversalParser:
    EXCLUDED_DIRS: set[str] = {
        "node_modules", "vendor", ".venv", "venv", "env", "site-packages",
        "dist", "build", "__pycache__", ".next", "out", "target", "bin", "obj",
        ".git", ".svn", ".hg", "generated", "gen", ".idea", ".vscode",
        ".pytest_cache", ".tox", ".eggs", ".pytest_cache",
        "bower_components", ".sass-cache", ".cache",
    }
    
    EXCLUDED_FILES: set[str] = {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "poetry.lock", "Pipfile.lock", "requirements.txt",
        "setup.py", "setup.cfg", "pyproject.toml", "Makefile",
        ".DS_Store", "Thumbs.db",
    }
    
    EXCLUDED_EXTENSIONS: set[str] = {
        ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg",
        ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
        ".mp3", ".mp4", ".wav", ".avi", ".mov",
        ".ttf", ".otf", ".woff", ".woff2",
        ".env", ".example",
    }
    
    MAX_FILE_SIZE = 512 * 1024  # 512KB max (reduced for faster parsing)
    
    def __init__(self, root: Path | None = None, workers: int = 4):
        self._root = root
        self._workers = min(workers, os.cpu_count() or 4)
        self._progress_callback: Callable[[str, int, int], None] | None = None

    @property
    def root(self) -> Path | None:
        return self._root

    @root.setter
    def root(self, value: Path | None):
        self._root = value

    def set_progress_callback(self, callback: Callable[[str, int, int], None] | None):
        self._progress_callback = callback

    def _report_progress(self, message: str, current: int, total: int):
        if self._progress_callback:
            self._progress_callback(message, current, total)

    def get_language(self, file_path: Path) -> str | None:
        ext = file_path.suffix.lower()
        if ext.startswith("."):
            return LANGUAGE_MAP.get(ext)
        return None

    def is_supported(self, file_path: Path) -> bool:
        return self.get_language(file_path) is not None

    def should_skip(self, file_path: Path, root: Path) -> bool:
        try:
            relative = file_path.relative_to(root)
        except ValueError:
            return True

        if relative.name in self.EXCLUDED_FILES:
            return True

        ext = file_path.suffix.lower()
        if ext in self.EXCLUDED_EXTENSIONS:
            return True

        parts = relative.parts
        for part in parts:
            if part in self.EXCLUDED_DIRS:
                return True

        try:
            stat = file_path.stat()
            if stat.st_size > self.MAX_FILE_SIZE:
                return True
            if stat.st_size == 0:
                return True
        except OSError:
            return True

        return False

    def _read_file(self, file_path: Path) -> tuple[str | None, str | None]:
        try:
            code = file_path.read_text(encoding="utf-8", errors="replace")
            return code, None
        except (OSError, UnicodeDecodeError) as e:
            return None, str(e)

    def parse_file(self, file_path: Path, root: Path) -> ParseResult:
        if self.should_skip(file_path, root):
            return ParseResult(functions=[], classes=[], errors=[])

        language = self.get_language(file_path)
        if language is None:
            return ParseResult(functions=[], classes=[], errors=[])

        code, error = self._read_file(file_path)
        if error:
            return ParseResult(functions=[], classes=[], errors=[f"{file_path}: {error}"])

        return self.parse_code(code, str(file_path), language)

    def parse_code(self, code: str, file_path: str, language: str) -> ParseResult:
        functions = []
        classes = []
        errors = []

        try:
            sg_root = SgRoot(code, language)
        except Exception as e:
            return ParseResult(functions=[], classes=[], errors=[f"{file_path}: {e}"])

        func_kinds = FUNCTION_NODES.get(language, [])
        for kind in func_kinds:
            try:
                for match in sg_root.root().find_all(kind=kind):
                    try:
                        func = self._extract_function(match, file_path, language, code)
                        if func:
                            functions.append(func)
                    except Exception as e:
                        errors.append(f"Function extraction error: {e}")
            except Exception as e:
                errors.append(f"Function find error ({kind}): {e}")

        class_kinds = CLASS_NODES.get(language, [])
        for kind in class_kinds:
            try:
                for match in sg_root.root().find_all(kind=kind):
                    try:
                        cls = self._extract_class(match, file_path, language, code)
                        if cls:
                            classes.append(cls)
                    except Exception as e:
                        errors.append(f"Class extraction error: {e}")
            except Exception as e:
                errors.append(f"Class find error ({kind}): {e}")

        imports = self._find_imports(sg_root, language)

        for func in functions:
            func.imports = imports

        return ParseResult(functions=functions, classes=classes, errors=errors)

    def _extract_function(self, match: Any, file_path: str, language: str, source: str) -> ParsedFunction | None:
        try:
            text = match.text()
            range_info = match.range()
            
            line_start = getattr(range_info.start, 'line', 0) or 0
            line_end = getattr(range_info.end, 'line', 0) or 0

            name = self._extract_name(match, language, text)
            if not name:
                return None

            func_id = self._make_function_id(file_path, name)

            signature = text.split("\n")[0] if text else text
            docstring = self._extract_docstring(match, source)
            calls = self._find_calls(match, language, source)
            params, returns = self._extract_params_and_returns(match, source)

            is_async = False
            decorators = []
            branches = []
            loops = []
            exception_handlers = []
            awaits = []
            raises = []

            if language == "python":
                try:
                    cf = self._extract_control_flow(text)
                    is_async = cf.get("is_async", False)
                    decorators = cf.get("decorators", [])
                    branches = cf.get("branches", [])
                    loops = cf.get("loops", [])
                    exception_handlers = cf.get("exception_handlers", [])
                    awaits = cf.get("awaits", [])
                    raises = cf.get("raises", [])
                except Exception:
                    pass

            return ParsedFunction(
                id=func_id, name=name, file_path=file_path,
                line_start=line_start, line_end=line_end,
                signature=signature, docstring=docstring, calls=calls,
                params=params, returns=returns, kind="function",
                is_async=is_async, decorators=decorators, branches=branches,
                loops=loops, exception_handlers=exception_handlers,
                awaits=awaits, raises=raises,
            )
        except Exception:
            return None

    def _extract_name(self, match: Any, language: str, text: str) -> str | None:
        try:
            if hasattr(match, "children"):
                for child in match.children():
                    if hasattr(child, "kind"):
                        kind = child.kind().lower()
                        if "identifier" in kind or "name" in kind:
                            name = child.text()
                            if name and name.isidentifier():
                                return name

            if language == "python" and "def " in text:
                start = text.index("def ") + 4
                end = text.index("(", start)
                return text[start:end].strip()
            
            return None
        except Exception:
            return None

    def _extract_docstring(self, match: Any, source: str) -> str:
        try:
            text = match.text()
            lines = text.split("\n")
            for line in lines[1:]:
                line = line.strip()
                if line.startswith('"""') or line.startswith("'''"):
                    return line.strip('"\'').strip()
                if line.startswith('"') or line.startswith("'"):
                    return line.strip('"\'').strip()
            return ""
        except Exception:
            return ""

    def _find_calls(self, match: Any, language: str, source: str) -> list[str]:
        call_kinds = CALL_NODES.get(language, [])
        calls = []

        for kind in call_kinds:
            try:
                for sub in match.find_all(kind=kind):
                    try:
                        name = self._extract_call_name(sub, language)
                        if name and name not in calls:
                            calls.append(name)
                    except Exception:
                        continue
            except Exception:
                continue

        return calls

    def _extract_call_name(self, match: Any, language: str) -> str | None:
        try:
            text = match.text()
            if "(" in text:
                name = text[:text.index("(")].strip().split(".")[-1]
                if name and name.isidentifier():
                    return name
            return text.split(".")[-1] if text.isidentifier() else None
        except Exception:
            return None

    def _find_imports(self, sg_root: Any, language: str) -> list[str]:
        imports = []
        import_kinds = IMPORT_NODES.get(language, [])

        for kind in import_kinds:
            try:
                for imp in sg_root.root().find_all(kind=kind):
                    try:
                        text = imp.text()
                        if "from " in text:
                            start = text.index("from ") + 5
                            end = text.index(" import") if " import" in text else len(text)
                            module = text[start:end].strip()
                        elif "import " in text:
                            module = text.replace("import ", "").strip()
                        else:
                            module = text.strip()
                        
                        if module and module not in imports:
                            imports.append(module)
                    except Exception:
                        continue
            except Exception:
                continue

        return imports

    def _extract_params_and_returns(self, match: Any, source: str) -> tuple[list[str], list[str]]:
        params = []
        returns = []

        try:
            text = match.text()

            if "(" in text and ")" in text:
                paren_start = text.index("(")
                paren_end = text.index(")")
                params_str = text[paren_start + 1:paren_end]
                for p in params_str.split(","):
                    p = p.strip().replace(",", "").split(":")[0].split("=")[0].strip()
                    if p and p not in ("self", "cls", "*args", "**kwargs") and p not in params:
                        params.append(p)

            if "return " in text:
                for line in text.split("\n"):
                    if "return " in line:
                        ret = line.split("return ", 1)[1].strip()
                        if ret and ret not in ("None", "pass"):
                            ret_clean = ret.split(",")[0].strip()
                            if ret_clean not in returns:
                                returns.append(ret_clean)

        except Exception:
            pass

        return params, returns

    def _extract_control_flow(self, text: str) -> dict[str, Any]:
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
            tree = ast.parse(text)
        except Exception:
            return result

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                result["is_async"] = True

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    try:
                        dec_name = getattr(decorator, "attr", None) or getattr(decorator, "id", None) or ""
                        if not dec_name:
                            dec_name = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
                        if dec_name:
                            result["decorators"].append(dec_name)
                    except Exception:
                        continue

            if isinstance(node, ast.If):
                try:
                    condition = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
                    result["branches"].append({"type": "if", "line": node.lineno, "condition": condition})
                except Exception:
                    result["branches"].append({"type": "if", "line": node.lineno, "condition": ""})

            if isinstance(node, (ast.For, ast.While)):
                result["loops"].append({
                    "type": "for" if isinstance(node, ast.For) else "while",
                    "line": node.lineno
                })

            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    exc_type = "Exception"
                    if handler.type:
                        try:
                            exc_type = ast.unparse(handler.type) if hasattr(ast, "unparse") else "Exception"
                        except Exception:
                            pass
                    result["exception_handlers"].append({"type": exc_type, "line": handler.lineno or 0})

            if isinstance(node, ast.Await):
                try:
                    await_val = ast.unparse(node.value) if hasattr(ast, "unparse") else ""
                    if await_val:
                        result["awaits"].append(await_val)
                except Exception:
                    continue

            if isinstance(node, ast.Raise):
                try:
                    if node.exc:
                        exc = ast.unparse(node.exc) if hasattr(ast, "unparse") else ""
                        if exc:
                            result["raises"].append(exc)
                except Exception:
                    continue

        return result

    def _extract_class(self, match: Any, file_path: str, language: str, source: str) -> ParsedClass | None:
        try:
            range_info = match.range()
            
            line_start = getattr(range_info.start, 'line', 0) or 0
            line_end = getattr(range_info.end, 'line', 0) or 0

            name = self._extract_class_name(match, language)
            if not name:
                return None

            class_id = self._make_class_id(file_path, name)

            bases = self._extract_bases(match, language)
            methods = self._extract_methods(match, language)
            attributes = self._extract_attributes(match, language)

            return ParsedClass(
                id=class_id, name=name, file_path=file_path,
                line_start=line_start, line_end=line_end,
                bases=bases, methods=methods, attributes=attributes, kind="class"
            )
        except Exception:
            return None

    def _extract_class_name(self, match: Any, language: str) -> str | None:
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
                end = text.index("(") if "(" in text else (text.index(":") if ":" in text else len(text))
                return text[start:end].strip()
            
            return None
        except Exception:
            return None

    def _extract_bases(self, match: Any, language: str) -> list[str]:
        bases = []
        try:
            text = match.text()
            if "(" in text:
                paren_start = text.index("(")
                paren_end = text.rindex(")") if ")" in text[paren_start:] else len(text)
                bases_str = text[paren_start + 1:paren_end]
                for base in bases_str.split(","):
                    base = base.strip().replace(",", "").split(":")[0].strip()
                    if base and base not in ("object", "Exception", "BaseException") and base not in bases:
                        bases.append(base)
        except Exception:
            pass
        return bases

    def _extract_methods(self, match: Any, language: str) -> list[str]:
        methods = []
        try:
            text = match.text()
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("def ") or line.startswith("async def "):
                    prefix = "def " if line.startswith("def ") else "async def "
                    func_start = len(prefix)
                    paren = line.index("(") if "(" in line else len(line)
                    name = line[func_start:paren].strip()
                    if name and not name.startswith("_") and name not in methods:
                        methods.append(name)
        except Exception:
            pass
        return methods

    def _extract_attributes(self, match: Any, language: str) -> list[str]:
        attrs = []
        try:
            text = match.text()
            for line in text.split("\n"):
                line = line.strip()
                if ": " in line and "=" in line:
                    attr = line.split("=")[0].strip().replace(":", "").strip()
                    if attr and not attr.startswith("_") and attr not in attrs:
                        attrs.append(attr)
        except Exception:
            pass
        return attrs

    def _make_function_id(self, file_path: str, function_name: str) -> str:
        content = f"{file_path}:{function_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _make_class_id(self, file_path: str, class_name: str) -> str:
        content = f"{file_path}:{class_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _parse_file_worker(self, args: tuple) -> ParseResult:
        file_path, root = args
        return self.parse_file(file_path, root)

    def parse_directory(self, root: Path) -> ParseResult:
        all_functions = []
        all_classes = []
        all_errors = []
        total_files = 0
        processed_files = 0

        files_to_process = []
        for file_path in root.rglob("*"):
            if file_path.is_file() and not self.should_skip(file_path, root):
                files_to_process.append(file_path)
                total_files += 1

        self._report_progress("Finding files", processed_files, total_files)

        with ThreadPoolExecutor(max_workers=self._workers) as executor:
            futures = {
                executor.submit(self._parse_file_worker, (fp, root)): fp
                for fp in files_to_process
            }

            for future in as_completed(futures):
                processed_files += 1
                self._report_progress("Parsing", processed_files, total_files)

                try:
                    result = future.result(timeout=30)
                    all_functions.extend(result.functions)
                    all_classes.extend(result.classes)
                    all_errors.extend(result.errors)
                except Exception as e:
                    all_errors.append(f"File parse error: {e}")

        return ParseResult(
            functions=all_functions,
            classes=all_classes,
            errors=all_errors
        )

    def get_file_hashes(self, root: Path) -> list[FileHash]:
        hashes = []
        for file_path in root.rglob("*"):
            if file_path.is_file() and not self.should_skip(file_path, root):
                try:
                    stat = file_path.stat()
                    content = file_path.read_bytes()
                    file_hash = hashlib.md5(content).hexdigest()
                    hashes.append(FileHash(
                        path=str(file_path),
                        mtime=stat.st_mtime,
                        size=stat.st_size,
                        hash=file_hash
                    ))
                except Exception:
                    continue
        return hashes
