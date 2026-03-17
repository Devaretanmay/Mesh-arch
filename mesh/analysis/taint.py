"""
Taint tracking for Mesh - Security-focused data flow analysis.

This module provides comprehensive taint tracking to detect security vulnerabilities
in codebases by tracking how untrusted data flows from sources to sinks.

Key concepts:
- Sources: Where untrusted data enters the system
- Sinks: Where data shouldn't reach without sanitization
- Sanitizers: Functions that clean/validate data
- Propagation: How taint flows through operations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default sources - where untrusted data enters the system
DEFAULT_SOURCES: set[str] = {
    # HTTP/User input
    "request",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "request.args",
    "request.form",
    "request.json",
    "request.headers",
    "request.params",
    "request.query",
    "request.body",
    "request.cookies",
    "request.files",
    "request.stream",
    "HTTPRequest",
    "HttpRequest",
    "IncomingMessage",
    "get_argument",
    "get_json",
    "get_form_data",
    "input",
    "raw_input",
    "sys.stdin",
    # File/Environment
    "open",
    "read",
    "readfile",
    "read_file",
    "os.environ",
    "os.getenv",
    "environ",
    "getenv",
    "os.environ.get",
    "environ.get",
    "env",
    "get_env",
    "stdin",
    "fileinput.input",
    # Database
    "cursor.fetch",
    "cursor.fetchone",
    "cursor.fetchall",
    "execute",
    "executemany",
    "fetchone",
    "fetchall",
    "sql_query",
    "raw_sql",
    # External APIs
    "api.get",
    "api.post",
    "api.request",
    "http.get",
    "http.post",
    "http.request",
    "fetch",
    "axios",
    "requests.get",
    "requests.post",
    "urllib.request",
    "urlopen",
    "subprocess",
    "os.popen",
    # Serialization
    "json.loads",
    "json.load",
    "pickle.loads",
    "pickle.load",
    "yaml.load",
    "yaml.safe_load",
    "toml.load",
    "marshal.loads",
    "eval",
    "exec",
    "compile",
    # User data
    "current_user",
    "get_user",
    "session",
    "cookie",
    "auth",
    "authentication",
    "authorization",
}

# Default sinks - where tainted data should not reach without sanitization
DEFAULT_SINKS: dict[str, set[str]] = {
    # SQL Injection sinks
    "sql": {
        "execute",
        "executemany",
        "cursor.execute",
        "cursor.executemany",
        "query",
        "raw_query",
        "sql",
        "raw_sql",
        "select",
        "insert",
        "update",
        "delete",
        "find",
        "find_one",
        "find_many",
        "aggregate",
        "bulk_write",
        "sqlalchemy",
        "text",
        "connection.execute",
    },
    # Code injection sinks
    "code_injection": {
        "eval",
        "exec",
        "compile",
        "exec_",
        "__import__",
        "importlib.import_module",
        "os.system",
        "os.popen",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.exec",
        "exec_cmd",
        "run_command",
        "shell",
    },
    # XSS/HTML sinks
    "xss": {
        "render",
        "render_template",
        "render_template_string",
        "html",
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "createElement",
        "document.write",
        "Response",
        "jsonify",
        "make_response",
        "redirect",
        "display",
        "show",
        "format",
        "format_html",
        " Markup",
    },
    # Path traversal sinks
    "path_traversal": {
        "open",
        "read",
        "write",
        "readfile",
        "writefile",
        "file",
        "file_exists",
        "path_exists",
        "os.path.join",
        "Path",
        "joinpath",
        "chmod",
        "chown",
        "unlink",
        "remove",
        "delete",
        "send_file",
        "send_from_directory",
    },
    # Command injection sinks
    "command_injection": {
        "system",
        "popen",
        "call",
        "run",
        "exec",
        "spawn",
        "execv",
        "execve",
        "popen4",
        "shell_exec",
        "shell_exec",
        "passthru",
    },
    # Logging sensitive data sinks
    "logging": {
        "log",
        "debug",
        "info",
        "warning",
        "error",
        "critical",
        "logger",
        "log.info",
        "log.debug",
        "log.error",
        "print",
        "console.log",
        "console.warn",
        "console.error",
        "stdout",
        "stderr",
        "write",
        "writeln",
        "sys.stdout.write",
        "sys.stderr.write",
    },
    # External API calls / data exfiltration
    "exfiltration": {
        "requests.post",
        "requests.get",
        "http.post",
        "http.get",
        "fetch",
        "axios",
        "urlopen",
        "urlretrieve",
        "urllib.request",
        "urllib2.request",
        "http.request",
        "httpclient",
        "httpclient.do",
        "send",
        "send_data",
        "transmit",
    },
    # File write / disk
    "file_write": {
        "write",
        "writefile",
        "write_file",
        "writefile",
        "save",
        "save_to",
        "persist",
        "store",
        "put",
        "put_object",
        "upload",
        "to_file",
        "dump",
        "dumpfile",
    },
    # SSRF - Server-Side Request Forgery
    "ssrf": {
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.request",
        "urllib.request",
        "urllib.urlopen",
        "urllib3.request",
        "httpx.get",
        "httpx.post",
        "httpx.request",
        "aiohttp.ClientSession.get",
        "aiohttp.ClientSession.post",
        "httplib.request",
        "http.client.request",
        "urlopen",
        "urlretrieve",
        "fetch",
        "curl",
        "wget",
        "http_get",
        "http_post",
        "make_request",
        "send_request",
        "client.request",
    },
    # XXE - XML External Entity
    "xxe": {
        "xml.etree.ElementTree.parse",
        "xml.etree.ElementTree.fromstring",
        "lxml.etree.parse",
        "lxml.etree.fromstring",
        "xml.dom.minidom.parse",
        "xml.dom.pulldom.parse",
        "xml.sax.parse",
        "xml.sax.make_parser",
        "etree.parse",
        "etree.fromstring",
        "parseString",
        "parse",
        "DOMParser",
        "SAXParser",
        "XMLParser",
    },
    # Insecure Deserialization
    "deserialization": {
        "pickle.loads",
        "pickle.load",
        "pickle.Unpickler",
        "yaml.load",
        "yaml.unsafe_load",
        "yaml.full_load",
        "json.loads",
        "marshal.loads",
        "eval",
        "exec",
        "unpickle",
        "deserialize",
        "unserialize",
        "unyaml",
    },
    # Insecure Randomness (for security-critical operations)
    "insecure_random": {
        "random.random",
        "random.randint",
        "random.randrange",
        "random.choice",
        "random.sample",
        "random.shuffle",
        "Math.random",
        "SecureRandom.next",
        "new SecureRandom()",
    },
    # Weak Cryptography
    "weak_crypto": {
        "hashlib.md5",
        "hashlib.sha1",
        "hashlib.sha224",
        "hmac.new",
        "hmac_md5",
        "hmac_sha1",
        "Crypto.Cipher",
        "DES.new",
        "ARC4.new",
        "RC4.new",
        "md5",
        "sha1",
        "sha",
        "MD5",
        "SHA1",
        "SHA",
        "Cipher",
        "Blowfish",
        "RC4",
        "ARC4",
    },
}

# Default sanitizers - functions that clean/validate data
DEFAULT_SANITIZERS: set[str] = {
    # Input validation
    "validate",
    "validate_input",
    "validate_email",
    "validate_password",
    "check",
    "verify",
    "verify_input",
    "verify_token",
    "is_valid",
    "is_valid_email",
    "is_valid_url",
    "is_valid_int",
    "sanitize",
    "sanitize_input",
    "clean",
    "clean_input",
    "escape",
    "escape_html",
    "escape_xml",
    "escape_json",
    "strip",
    "strip_tags",
    "remove_tags",
    # Encoding/escaping
    "html_escape",
    "htmlentities",
    "urlencode",
    "urllib.parse.quote",
    "json.dumps",
    "jsonify",
    "dumps",
    "base64_encode",
    "base64.b64encode",
    "b64encode",
    "hex_encode",
    "hash",
    "hash_password",
    # SQL
    "escape_sql",
    "quote",
    "adapt",
    "parameterize",
    "sql_escape",
    "mysql_escape",
    "pg_escape",
    "prepare",
    "param",
    "bind",
    # Cryptography
    "encrypt",
    "decrypt",
    "hash",
    "hash_password",
    "bcrypt",
    "hmac",
    "sign",
    "verify_signature",
    "encode",
    "decode",
    # Type coercion
    "int",
    "float",
    "str",
    "bool",
    "list",
    "dict",
    "to_int",
    "to_float",
    "to_string",
    "parse_int",
    # Framework sanitizers
    "flask.escape",
    "markupsafe.escape",
    "jinja2.escape",
    "django.utils.safestring.mark_safe",
    "werkzeug.security.generate_password_hash",
}

# Patterns for detecting sensitive data
SENSITIVE_PATTERNS: dict[str, re.Pattern] = {
    "password": re.compile(r"password|passwd|pwd|pass", re.I),
    "secret": re.compile(r"secret|private|key|api_?key|apikey|token|auth", re.I),
    "session": re.compile(r"session|session_?id|sid", re.I),
    "financial": re.compile(
        r"credit_?card|card_?number|cvv|card|cvv2|ssn|social_?security", re.I
    ),
    "personal": re.compile(
        r"email|phone|mobile|address|dob|date_?of_?birth|age|gender", re.I
    ),
    "crypto": re.compile(r"private_?key|secret_?key|secret|wallet|seed|mnemonic", re.I),
}


@dataclass
class TaintSource:
    """Represents a source of potentially tainted data."""

    name: str
    file_path: str
    line: int
    function: str | None = None
    variable: str | None = None
    category: str = "user_input"


@dataclass
class TaintSink:
    """Represents a sink where tainted data should not reach."""

    name: str
    file_path: str
    line: int
    function: str | None = None
    category: str = "sql"


@dataclass
class TaintFlow:
    """Represents a flow of taint from source to sink."""

    source: TaintSource
    sink: TaintSink
    path: list[str] = field(default_factory=list)
    sanitized: bool = False
    sanitizer: str | None = None


@dataclass
class TaintViolation:
    """Represents a taint security violation."""

    kind: str  # sql_injection, xss, etc
    severity: str  # error, warning
    message: str
    file_path: str
    line: int
    source: TaintSource | None = None
    sink: TaintSink | None = None
    fix_hint: str = ""
    related_files: list[str] = field(default_factory=list)


class TaintTracker:
    """
    Tracks taint flow through a codebase.

    Uses AST analysis to find:
    - Sources of untrusted data
    - Sinks where data shouldn't go
    - Sanitizers that clean data
    - Actual flows between them
    """

    def __init__(
        self,
        codebase_root: Path,
        custom_sources: set[str] | None = None,
        custom_sinks: dict[str, set[str]] | None = None,
        custom_sanitizers: set[str] | None = None,
    ):
        self._root = codebase_root
        self._sources = custom_sources or DEFAULT_SOURCES
        self._sinks = custom_sinks or DEFAULT_SINKS
        self._sanitizers = custom_sanitizers or DEFAULT_SANITIZERS
        self._violations: list[TaintViolation] = []

    @property
    def sources(self) -> set[str]:
        return self._sources

    @property
    def sinks(self) -> dict[str, set[str]]:
        return self._sinks

    @property
    def sanitizers(self) -> set[str]:
        return self._sanitizers

    def load_config(self) -> dict[str, Any]:
        """Load custom taint configuration from .mesh/config.json."""
        config_path = self._root / ".mesh" / "config.json"
        if config_path.exists():
            try:
                import json

                return json.loads(config_path.read_text())
            except Exception:
                pass
        return {}

    def is_source(self, name: str) -> bool:
        """Check if a function/variable is a source of untrusted data."""
        name_lower = name.lower()

        # Check exact matches
        if name_lower in self._sources:
            return True

        # Check patterns (e.g., "request.args")
        for source in self._sources:
            if "." in source:
                if name_lower.endswith("." + source.split(".")[-1]):
                    return True

        return False

    def is_sink(self, name: str, category: str | None = None) -> tuple[bool, str]:
        """
        Check if a function is a sink.

        Returns:
            Tuple of (is_sink, category)
        """
        name_lower = name.lower()

        # Check each category
        for cat, sinks in self._sinks.items():
            if category and category != cat:
                continue
            for sink in sinks:
                if name_lower == sink or name_lower.endswith("." + sink):
                    return True, cat

        return False, ""

    def is_sanitizer(self, name: str) -> bool:
        """Check if a function is a sanitizer."""
        name_lower = name.lower()

        if name_lower in self._sanitizers:
            return True

        for sanitizer in self._sanitizers:
            if "." in sanitizer:
                if name_lower.endswith("." + sanitizer.split(".")[-1]):
                    return True

        return False

    def find_sensitive_data(self, name: str) -> list[str]:
        """Check if a variable name contains sensitive data patterns."""
        matches = []
        name_lower = name.lower()

        for pattern_name, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(name_lower):
                matches.append(pattern_name)

        return matches

    def detect_violations(
        self,
        call_graph,
        data_flow_graph,
    ) -> list[TaintViolation]:
        """
        Detect taint violations by analyzing call and data flow graphs.

        Args:
            call_graph: The call graph
            data_flow_graph: The data flow graph

        Returns:
            List of detected violations
        """
        violations: list[TaintViolation] = []

        # Build node lookup
        nodes = {n.get("id"): n for n in call_graph.nodes() if n.get("id")}

        # Find all sources and sinks in the graph
        source_nodes: list[dict] = []
        sink_nodes: list[tuple[dict, str]] = []  # (node, category)

        for node_id, node in nodes.items():
            name = node.get("name", "")

            # Check if it's a source
            if self.is_source(name):
                source_nodes.append(node)

            # Check if it's a sink
            is_sink, category = self.is_sink(name)
            if is_sink:
                sink_nodes.append((node, category))

        # For each source, trace flows to sinks
        for source_node in source_nodes:
            source_name = source_node.get("name", "")
            source_file = source_node.get("file_path", "")
            source_line = source_node.get("line_start", 0)

            # Check if source handles sensitive data
            sensitive_types = self.find_sensitive_data(source_name)

            # Find paths from source to sinks using call graph
            reachable = self._find_reachable_sinks(call_graph, source_node, sink_nodes)

            for sink_node, path in reachable:
                sink_name = sink_node.get("name", "")
                sink_file = sink_node.get("file_path", "")
                sink_line = sink_node.get("line_start", 0)
                category = sink_node.get("category", "unknown")

                # Check if there's a sanitizer in the path
                sanitizers_in_path = [
                    n for n in path if self.is_sanitizer(n.get("name", ""))
                ]

                # Determine violation kind based on sink category
                violation_kind = self._get_violation_kind(category)

                # Check for sensitive data involvement
                sensitive_msg = ""
                if sensitive_types:
                    sensitive_msg = f" (sensitive: {', '.join(sensitive_types)})"

                # Determine severity based on sink category + sanitizer presence
                severity = self._get_severity(category, sanitizers_in_path)

                # Create violation
                violation = TaintViolation(
                    kind=violation_kind,
                    severity=severity,
                    message=f"Tainted data flows to {category} sink: {source_name} → {sink_name}{sensitive_msg}",
                    file_path=sink_file,
                    line=sink_line,
                    source=TaintSource(
                        name=source_name,
                        file_path=source_file,
                        line=source_line,
                    ),
                    sink=TaintSink(
                        name=sink_name,
                        file_path=sink_file,
                        line=sink_line,
                        category=category,
                    ),
                    fix_hint=self._get_fix_hint(category, sanitizers_in_path),
                    related_files=[source_file],
                )
                violations.append(violation)

        self._violations = violations
        return violations

    def _find_reachable_sinks(
        self,
        call_graph,
        source_node: dict,
        sink_nodes: list[tuple[dict, str]],
    ) -> list[tuple[dict, list[dict]]]:
        """
        Find sinks reachable from a source through the call graph.

        Returns:
            List of (sink_node, path_from_source) tuples
        """
        source_id = source_node.get("id", "")
        if not source_id:
            return []

        reachable: list[tuple[dict, list[dict]]] = []

        # BFS to find all reachable nodes
        visited: set[str] = set()
        queue: list[tuple[str, list[dict]]] = [(source_id, [source_node])]

        while queue:
            current_id, path = queue.pop(0)

            if current_id in visited:
                continue
            visited.add(current_id)

            # Check if current node is a sink
            current_name = ""
            for node, category in sink_nodes:
                if node.get("id") == current_id:
                    current_name = node.get("name", "")
                    if current_name:
                        reachable.append((node, path))
                    break

            # Find callees
            for edge in call_graph.edges():
                if isinstance(edge, dict):
                    if edge.get("from_id") == current_id:
                        callee_id = edge.get("to_id", "")

                        # Find the callee node
                        callee_node = None
                        for node, _ in sink_nodes:
                            if node.get("id") == callee_id:
                                callee_node = node
                                break

                        if callee_id not in visited and callee_node:
                            new_path = path + [callee_node]
                            queue.append((callee_id, new_path))

        return reachable

    def _get_violation_kind(self, category: str) -> str:
        """Map sink category to violation kind."""
        mapping = {
            "sql": "sql_injection",
            "code_injection": "code_injection",
            "xss": "xss",
            "path_traversal": "path_traversal",
            "command_injection": "command_injection",
            "logging": "sensitive_data_logging",
            "exfiltration": "data_exfiltration",
            "file_write": "arbitrary_file_write",
            "ssrf": "ssrf",
            "xxe": "xxe",
            "deserialization": "insecure_deserialization",
            "insecure_random": "insecure_random",
            "weak_crypto": "weak_crypto",
        }
        return mapping.get(category, "unsafe_data_flow")

    def _get_severity(self, category: str, sanitizers: list[dict]) -> str:
        """Determine severity based on sink category and sanitizers."""
        high_severity = {
            "sql",
            "code_injection",
            "command_injection",
            "deserialization",
            "xxe",
            "ssrf",
        }
        medium_severity = {
            "xss",
            "path_traversal",
            "exfiltration",
            "file_write",
        }
        low_severity = {
            "logging",
            "insecure_random",
            "weak_crypto",
        }

        if sanitizers:
            return "warning"

        if category in high_severity:
            return "error"
        elif category in medium_severity:
            return "warning"
        elif category in low_severity:
            return "info"
        return "warning"

    def _get_fix_hint(self, category: str, sanitizers: list[dict]) -> str:
        """Get fix hint for a violation."""
        hints = {
            "sql": "Use parameterized queries or ORM. Sanitize input with parameterized()",
            "code_injection": "Never use eval() or exec() with user input. Use ast.literal_eval() for safe parsing",
            "xss": "Use template escaping or html.escape() before rendering user data",
            "path_traversal": "Validate and sanitize file paths. Use os.path.basename() to extract filename",
            "command_injection": "Use subprocess with shell=False and pass arguments as list",
            "logging": "Redact sensitive data before logging. Use redaction libraries",
            "exfiltration": "Validate and sanitize data before external API calls",
            "file_write": "Validate file paths and use allowlist for permitted directories",
            "ssrf": "Validate URLs against allowlist. Use urlparse() to check host before requesting",
            "xxe": "Use safe XML parsers: lxml with no_ents=True, or defusedxml",
            "deserialization": "Never unpickle untrusted data. Use json instead of pickle",
            "insecure_random": "Use secrets.token_* for security-critical randomness",
            "weak_crypto": "Use hashlib.sha256 or hashlib.bcrypt. Avoid md5/sha1 for security",
        }

        if sanitizers:
            hint = hints.get(category, "Review and improve sanitization")
            return f"{hint}. Current sanitizer may be insufficient."

        return hints.get(category, "Sanitize data before use")


def detect_taint_violations(
    call_graph,
    data_flow_graph,
    codebase_root: Path | None = None,
) -> list[dict]:
    """
    Detect taint-related security violations.

    Args:
        call_graph: The call graph
        data_flow_graph: The data flow graph
        codebase_root: Root of the codebase (for loading config)

    Returns:
        List of violation dicts
    """
    # Load custom config if available
    custom_config = {}
    if codebase_root:
        config_path = codebase_root / ".mesh" / "config.json"
        if config_path.exists():
            try:
                import json

                custom_config = json.loads(config_path.read_text())
            except Exception:
                pass

    # Get custom patterns from config
    taint_config = custom_config.get("taint_tracking", {})
    custom_sources = set(taint_config.get("sources", []))
    custom_sinks_dict = taint_config.get("sinks", {})
    custom_sanitizers = set(taint_config.get("sanitizers", []))

    # Convert sinks dict to the expected format
    custom_sinks: dict[str, set[str]] = {}
    for cat, sinks in custom_sinks_dict.items():
        custom_sinks[cat] = set(sinks) if isinstance(sinks, list) else sinks

    # Create tracker
    root = codebase_root or Path(".")
    tracker = TaintTracker(
        root,
        custom_sources=custom_sources or None,
        custom_sinks=custom_sinks or None,
        custom_sanitizers=custom_sanitizers or None,
    )

    # Detect violations
    violations = tracker.detect_violations(call_graph, data_flow_graph)

    # Convert to dict format
    result = []
    for v in violations:
        result.append(
            {
                "kind": v.kind,
                "severity": v.severity,
                "message": v.message,
                "file_path": v.file_path,
                "line": v.line,
                "related_files": v.related_files,
                "fix_hint": v.fix_hint,
            }
        )

    return result
