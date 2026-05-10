"""
Source and Sink Database for security analysis.

Contains known security-relevant sources (user input entry points) and
sinks (dangerous operations) for Python and JavaScript/TypeScript.

Each entry includes:
  - name: human-readable identifier
  - language: "python" | "javascript" | "typescript" | "any"
  - pattern: regex to match in source code
  - risk_level: "critical" | "high" | "medium" | "low"
  - associated_vuln_classes: list of CWE/OWASP identifiers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SecurityEndpoint:
    """A security-relevant code pattern (source or sink)."""
    name: str
    language: str  # "python", "javascript", "typescript", "any"
    pattern: str   # regex pattern
    risk_level: str  # "critical", "high", "medium", "low"
    associated_vuln_classes: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "language": self.language,
            "pattern": self.pattern,
            "risk_level": self.risk_level,
            "associated_vuln_classes": self.associated_vuln_classes,
            "description": self.description,
        }


# ═══════════════════════════════════════════════════════════════════
#  PYTHON SOURCES  (user-controlled input entry points)
# ═══════════════════════════════════════════════════════════════════

PYTHON_SOURCES: list[SecurityEndpoint] = [
    SecurityEndpoint(
        name="request.args",
        language="python",
        pattern=r"request\.args",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89", "CWE-78"],
        description="Flask/Django query string parameters",
    ),
    SecurityEndpoint(
        name="request.form",
        language="python",
        pattern=r"request\.form",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89", "CWE-78"],
        description="Flask/Django form data",
    ),
    SecurityEndpoint(
        name="request.json",
        language="python",
        pattern=r"request\.json",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89", "CWE-502"],
        description="Flask/Django JSON body",
    ),
    SecurityEndpoint(
        name="request.data",
        language="python",
        pattern=r"request\.data",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89"],
        description="Flask raw request body",
    ),
    SecurityEndpoint(
        name="request.headers",
        language="python",
        pattern=r"request\.headers",
        risk_level="medium",
        associated_vuln_classes=["CWE-79", "CWE-113"],
        description="HTTP headers (Host, Referer, User-Agent)",
    ),
    SecurityEndpoint(
        name="input()",
        language="python",
        pattern=r"\binput\s*(?:\s*\()?",
        risk_level="medium",
        associated_vuln_classes=["CWE-78", "CWE-89"],
        description="Built-in input() function",
    ),
    SecurityEndpoint(
        name="sys.argv",
        language="python",
        pattern=r"sys\.argv",
        risk_level="medium",
        associated_vuln_classes=["CWE-78", "CWE-88"],
        description="Command-line arguments",
    ),
    SecurityEndpoint(
        name="os.environ",
        language="python",
        pattern=r"os\.environ",
        risk_level="medium",
        associated_vuln_classes=["CWE-78", "CWE-99"],
        description="Environment variables",
    ),
    SecurityEndpoint(
        name="flask.request",
        language="python",
        pattern=r"flask\.request|from\s+flask\s+import\s+.*request",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89"],
        description="Flask request object",
    ),
    SecurityEndpoint(
        name="django.request",
        language="python",
        pattern=r"django\.request|request\.(GET|POST|PUT|DELETE|PATCH)",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89"],
        description="Django request object",
    ),
    SecurityEndpoint(
        name="open().read()",
        language="python",
        pattern=r"open\s*(?:\s*\()?.*\)\.read|open\s*(?:\s*\()?[^)]*\)\.readlines",
        risk_level="medium",
        associated_vuln_classes=["CWE-22", "CWE-73"],
        description="Reading from file - path traversal risk",
    ),
    SecurityEndpoint(
        name="pickle.loads()",
        language="python",
        pattern=r"pickle\.loads?\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-502"],
        description="Deserializing untrusted pickle data",
    ),
    SecurityEndpoint(
        name="yaml.load()",
        language="python",
        pattern=r"yaml\.load\s*(?:\s*\()?(?!.*Loader\s*=\s*yaml\.SafeLoader)",
        risk_level="critical",
        associated_vuln_classes=["CWE-502"],
        description="YAML deserialization without SafeLoader",
    ),
    SecurityEndpoint(
        name="json.loads()",
        language="python",
        pattern=r"json\.loads\s*(?:\s*\()?",
        risk_level="low",
        associated_vuln_classes=["CWE-502"],
        description="JSON deserialization (low risk alone)",
    ),
    SecurityEndpoint(
        name="request.view_args",
        language="python",
        pattern=r"request\.view_args",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89"],
        description="Flask URL route parameters",
    ),
]

# ═══════════════════════════════════════════════════════════════════
#  PYTHON SINKS  (dangerous operations)
# ═══════════════════════════════════════════════════════════════════

PYTHON_SINKS: list[SecurityEndpoint] = [
    SecurityEndpoint(
        name="cursor.execute()",
        language="python",
        pattern=r"\.execute\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-89"],
        description="SQL query execution - SQL injection risk",
    ),
    SecurityEndpoint(
        name="os.system()",
        language="python",
        pattern=r"os\.system\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="OS command execution",
    ),
    SecurityEndpoint(
        name="subprocess.call()",
        language="python",
        pattern=r"subprocess\.call\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="Subprocess command execution",
    ),
    SecurityEndpoint(
        name="subprocess.run()",
        language="python",
        pattern=r"subprocess\.run\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="Subprocess command execution",
    ),
    SecurityEndpoint(
        name="subprocess.Popen()",
        language="python",
        pattern=r"subprocess\.Popen\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="Subprocess command execution",
    ),
    SecurityEndpoint(
        name="eval()",
        language="python",
        pattern=r"\beval\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-95", "CWE-78"],
        description="Dynamic code evaluation",
    ),
    SecurityEndpoint(
        name="exec()",
        language="python",
        pattern=r"\bexec\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-95", "CWE-78"],
        description="Dynamic code execution",
    ),
    SecurityEndpoint(
        name="open(path, 'w')",
        language="python",
        pattern=r"open\s*(?:\s*\()?[^)]*['\"]w['\"]",
        risk_level="high",
        associated_vuln_classes=["CWE-22", "CWE-434"],
        description="File write - path traversal risk",
    ),
    SecurityEndpoint(
        name="pickle.dumps()",
        language="python",
        pattern=r"pickle\.dumps?\s*(?:\s*\()?",
        risk_level="medium",
        associated_vuln_classes=["CWE-502"],
        description="Pickle serialization (if exposed)",
    ),
    SecurityEndpoint(
        name="yaml.dump()",
        language="python",
        pattern=r"yaml\.dump\s*(?:\s*\()?",
        risk_level="medium",
        associated_vuln_classes=["CWE-502"],
        description="YAML serialization",
    ),
    SecurityEndpoint(
        name="render_template_string()",
        language="python",
        pattern=r"render_template_string\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-94"],
        description="Server-side template injection (SSTI)",
    ),
    SecurityEndpoint(
        name="redirect()",
        language="python",
        pattern=r"\bredirect\s*(?:\s*\()?",
        risk_level="medium",
        associated_vuln_classes=["CWE-601"],
        description="URL redirect - open redirect risk",
    ),
    SecurityEndpoint(
        name="send_file()",
        language="python",
        pattern=r"send_file\s*(?:\s*\()?",
        risk_level="high",
        associated_vuln_classes=["CWE-22"],
        description="File serving - path traversal risk",
    ),
    SecurityEndpoint(
        name="marshal.loads()",
        language="python",
        pattern=r"marshal\.loads?\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-502"],
        description="Marshal deserialization",
    ),
    SecurityEndpoint(
        name="shelve.open()",
        language="python",
        pattern=r"shelve\.open\s*(?:\s*\()?",
        risk_level="high",
        associated_vuln_classes=["CWE-502"],
        description="Shelve database (uses pickle internally)",
    ),
    SecurityEndpoint(
        name="make_response()",
        language="python",
        pattern=r"make_response\s*(?:\s*\()?",
        risk_level="low",
        associated_vuln_classes=["CWE-113"],
        description="Flask response - header injection risk",
    ),
]

# ═══════════════════════════════════════════════════════════════════
#  JAVASCRIPT/TYPESCRIPT SOURCES
# ═══════════════════════════════════════════════════════════════════

JS_SOURCES: list[SecurityEndpoint] = [
    SecurityEndpoint(
        name="req.query",
        language="javascript",
        pattern=r"req\.query",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89"],
        description="Express query string parameters",
    ),
    SecurityEndpoint(
        name="req.body",
        language="javascript",
        pattern=r"req\.body",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89", "CWE-502"],
        description="Express request body",
    ),
    SecurityEndpoint(
        name="req.params",
        language="javascript",
        pattern=r"req\.params",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-89"],
        description="Express URL route parameters",
    ),
    SecurityEndpoint(
        name="req.headers",
        language="javascript",
        pattern=r"req\.headers",
        risk_level="medium",
        associated_vuln_classes=["CWE-79", "CWE-113"],
        description="HTTP headers",
    ),
    SecurityEndpoint(
        name="document.location",
        language="javascript",
        pattern=r"document\.location",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-601"],
        description="Browser document location",
    ),
    SecurityEndpoint(
        name="window.location",
        language="javascript",
        pattern=r"window\.location",
        risk_level="high",
        associated_vuln_classes=["CWE-79", "CWE-601"],
        description="Browser window location",
    ),
    SecurityEndpoint(
        name="localStorage",
        language="javascript",
        pattern=r"localStorage\.(getItem|key)",
        risk_level="medium",
        associated_vuln_classes=["CWE-79"],
        description="Web Storage API - localStorage",
    ),
    SecurityEndpoint(
        name="sessionStorage",
        language="javascript",
        pattern=r"sessionStorage\.(getItem|key)",
        risk_level="medium",
        associated_vuln_classes=["CWE-79"],
        description="Web Storage API - sessionStorage",
    ),
    SecurityEndpoint(
        name="URLSearchParams",
        language="javascript",
        pattern=r"URLSearchParams",
        risk_level="medium",
        associated_vuln_classes=["CWE-79"],
        description="URL search params parsing",
    ),
    SecurityEndpoint(
        name="fetch().then()",
        language="javascript",
        pattern=r"fetch\s*(?:\s*\()?.*\)\s*\.\s*then",
        risk_level="medium",
        associated_vuln_classes=["CWE-918", "CWE-79"],
        description="Fetch API response handling",
    ),
    SecurityEndpoint(
        name="document.cookie",
        language="javascript",
        pattern=r"document\.cookie",
        risk_level="medium",
        associated_vuln_classes=["CWE-79", "CWE-1004"],
        description="Cookie access",
    ),
    SecurityEndpoint(
        name="location.hash",
        language="javascript",
        pattern=r"location\.hash",
        risk_level="medium",
        associated_vuln_classes=["CWE-79"],
        description="URL hash fragment",
    ),
    SecurityEndpoint(
        name="postMessage",
        language="javascript",
        pattern=r"addEventListener\s*(?:\s*\()?\s*['\"]message['\"]",
        risk_level="medium",
        associated_vuln_classes=["CWE-345"],
        description="Cross-origin message receiving",
    ),
]

# ═══════════════════════════════════════════════════════════════════
#  JAVASCRIPT/TYPESCRIPT SINKS
# ═══════════════════════════════════════════════════════════════════

JS_SINKS: list[SecurityEndpoint] = [
    SecurityEndpoint(
        name="eval()",
        language="javascript",
        pattern=r"\beval\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-95"],
        description="JavaScript eval - code injection",
    ),
    SecurityEndpoint(
        name="Function()",
        language="javascript",
        pattern=r"\bnew\s+Function\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-95"],
        description="Dynamic function creation",
    ),
    SecurityEndpoint(
        name="innerHTML",
        language="javascript",
        pattern=r"\.innerHTML\s*=",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="DOM innerHTML assignment - XSS risk",
    ),
    SecurityEndpoint(
        name="document.write()",
        language="javascript",
        pattern=r"document\.write(ln)?\s*(?:\s*\()?",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="document.write - XSS risk",
    ),
    SecurityEndpoint(
        name="insertAdjacentHTML()",
        language="javascript",
        pattern=r"\.insertAdjacentHTML\s*(?:\s*\()?",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="DOM insertion - XSS risk",
    ),
    SecurityEndpoint(
        name="$.html()",
        language="javascript",
        pattern=r"\$\s*(?:\s*\()?[^)]*\)\s*\.\s*html\s*(?:\s*\()?",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="jQuery .html() - XSS risk",
    ),
    SecurityEndpoint(
        name="child_process.exec()",
        language="javascript",
        pattern=r"(child_process|require\s*(?:\s*\()?\s*['\"]child_process['\"]\s*\))\s*\.\s*exec\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="Node.js OS command execution",
    ),
    SecurityEndpoint(
        name="child_process.spawn()",
        language="javascript",
        pattern=r"(child_process|require\s*(?:\s*\()?\s*['\"]child_process['\"]\s*\))\s*\.\s*spawn\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="Node.js OS command spawning",
    ),
    SecurityEndpoint(
        name="child_process.execSync()",
        language="javascript",
        pattern=r"(child_process|require\s*(?:\s*\()?\s*['\"]child_process['\"]\s*\))\s*\.\s*execSync\s*(?:\s*\()?",
        risk_level="critical",
        associated_vuln_classes=["CWE-78"],
        description="Node.js synchronous OS command execution",
    ),
    SecurityEndpoint(
        name="outerHTML",
        language="javascript",
        pattern=r"\.outerHTML\s*=",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="DOM outerHTML assignment - XSS risk",
    ),
    SecurityEndpoint(
        name="setAttribute(on*)",
        language="javascript",
        pattern=r"setAttribute\s*(?:\s*\()?\s*['\"]on",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="Setting event handler attributes",
    ),
    SecurityEndpoint(
        name="dangerouslySetInnerHTML",
        language="javascript",
        pattern=r"dangerouslySetInnerHTML",
        risk_level="high",
        associated_vuln_classes=["CWE-79"],
        description="React dangerouslySetInnerHTML prop",
    ),
    SecurityEndpoint(
        name="fs.readFile()",
        language="javascript",
        pattern=r"fs\.\s*readFile\s*(?:\s*\()?",
        risk_level="medium",
        associated_vuln_classes=["CWE-22"],
        description="Node.js file read - path traversal risk",
    ),
    SecurityEndpoint(
        name="fs.writeFile()",
        language="javascript",
        pattern=r"fs\.\s*writeFile\s*(?:\s*\()?",
        risk_level="high",
        associated_vuln_classes=["CWE-22"],
        description="Node.js file write - path traversal risk",
    ),
    SecurityEndpoint(
        name="JSON.parse()",
        language="javascript",
        pattern=r"JSON\.parse\s*(?:\s*\()?",
        risk_level="low",
        associated_vuln_classes=["CWE-502"],
        description="JSON parsing (low risk, but prototype pollution possible)",
    ),
    SecurityEndpoint(
        name="res.send()",
        language="javascript",
        pattern=r"res\.\s*send\s*(?:\s*\()?",
        risk_level="low",
        associated_vuln_classes=["CWE-113"],
        description="Express response send - header injection risk",
    ),
    SecurityEndpoint(
        name="res.redirect()",
        language="javascript",
        pattern=r"res\.\s*redirect\s*(?:\s*\()?",
        risk_level="medium",
        associated_vuln_classes=["CWE-601"],
        description="Express redirect - open redirect risk",
    ),
]

# ═══════════════════════════════════════════════════════════════════
#  COMBINED LOOKUP HELPERS
# ═══════════════════════════════════════════════════════════════════

ALL_SOURCES: list[SecurityEndpoint] = PYTHON_SOURCES + JS_SOURCES
ALL_SINKS: list[SecurityEndpoint] = PYTHON_SINKS + JS_SINKS


def get_sources(language: str | None = None) -> list[SecurityEndpoint]:
    """Get sources, optionally filtered by language."""
    if language is None:
        return list(ALL_SOURCES)
    lang = language.lower()
    return [s for s in ALL_SOURCES if s.language == lang or s.language == "any"]


def get_sinks(language: str | None = None) -> list[SecurityEndpoint]:
    """Get sinks, optionally filtered by language."""
    if language is None:
        return list(ALL_SINKS)
    lang = language.lower()
    return [s for s in ALL_SINKS if s.language == lang or s.language == "any"]


def get_endpoint_by_name(name: str) -> SecurityEndpoint | None:
    """Look up a source or sink by name."""
    for ep in ALL_SOURCES + ALL_SINKS:
        if ep.name == name:
            return ep
    return None


def get_critical_sinks(language: str | None = None) -> list[SecurityEndpoint]:
    """Get only critical-risk sinks."""
    sinks = get_sinks(language)
    return [s for s in sinks if s.risk_level == "critical"]


def match_source(line: str, language: str | None = None) -> list[SecurityEndpoint]:
    """Find all source patterns that match a line of code."""
    import re
    matches = []
    for src in get_sources(language):
        if re.search(src.pattern, line):
            matches.append(src)
    return matches


def match_sink(line: str, language: str | None = None) -> list[SecurityEndpoint]:
    """Find all sink patterns that match a line of code."""
    import re
    matches = []
    for sink in get_sinks(language):
        if re.search(sink.pattern, line):
            matches.append(sink)
    return matches
