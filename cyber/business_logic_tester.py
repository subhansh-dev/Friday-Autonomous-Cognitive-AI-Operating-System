"""
business_logic_tester.py — Business Logic Security Testing
Discovers application-specific invariants, generates fuzzers, detects violations.
Inspired by Shannon Pro's 4-phase approach.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import requests

logger = logging.getLogger("friday.business_logic")


@dataclass
class Invariant:
    """A security invariant that must hold for the application to be secure."""
    id: str
    description: str
    endpoint: str
    method: str
    invariant_type: str  # authorization, multi_tenancy, state_machine, business_rule
    check_field: str = ""
    expected_behavior: str = ""
    confidence: float = 0.5


@dataclass
class Fuzzer:
    """A targeted test scenario designed to violate an invariant."""
    id: str
    invariant_id: str
    description: str
    request_method: str
    request_url: str
    request_headers: dict = field(default_factory=dict)
    request_body: dict = field(default_factory=dict)
    expected_status: int = 0
    expected_behavior: str = ""


@dataclass
class Violation:
    """A confirmed invariant violation."""
    invariant: Invariant
    fuzzer: Fuzzer
    actual_status: int
    actual_response: str
    evidence: str
    severity: str = "high"

    def to_finding(self) -> dict:
        return {
            "agent": "BUSINESS_LOGIC",
            "vuln_class": f"Business Logic: {self.invariant.invariant_type}",
            "finding_id": f"bizlogic_{self.invariant.id}_{self.fuzzer.id}",
            "file_path": self.invariant.endpoint,
            "confidence": "confirmed",
            "cvss_score": {"critical": 9.5, "high": 8.0, "medium": 6.0}.get(self.severity, 7.0),
            "summary": f"Business logic violation: {self.invariant.description}",
            "detail": (f"Endpoint: {self.invariant.method} {self.invariant.endpoint}\n"
                      f"Expected: {self.invariant.expected_behavior}\n"
                      f"Actual: {self.evidence}\n"
                      f"Request: {self.fuzzer.description}"),
            "target": self.invariant.endpoint,
            "exploit_evidence": self.evidence,
            "exploit_poc": [
                f"{self.fuzzer.request_method} {self.fuzzer.request_url}",
                f"Headers: {json.dumps(self.fuzzer.request_headers)}",
                f"Body: {json.dumps(self.fuzzer.request_body)}" if self.fuzzer.request_body else "",
                f"Response: {self.actual_status} — {self.actual_response[:200]}",
            ],
        }


class InvariantDiscoverer:
    """Phase 1: Discover security invariants from API routes and code."""

    # Common invariant patterns by endpoint characteristic
    ENDPOINT_PATTERNS = {
        "user": [
            Invariant("", "User can only access own profile", "", "GET",
                     "authorization", "user_id", "403 for other user's data"),
            Invariant("", "User can only modify own data", "", "PUT",
                     "authorization", "user_id", "403 for other user's data"),
        ],
        "admin": [
            Invariant("", "Admin endpoints require admin role", "", "GET",
                     "authorization", "role", "403 for non-admin users"),
        ],
        "order": [
            Invariant("", "Users can only view own orders", "", "GET",
                     "authorization", "user_id", "403 for other user's orders"),
            Invariant("", "Order amount cannot be negative", "", "POST",
                     "business_rule", "amount", "400 for negative amounts"),
        ],
        "transfer": [
            Invariant("", "Transfer amount must be positive", "", "POST",
                     "business_rule", "amount", "400 for zero/negative"),
            Invariant("", "Cannot transfer to same account", "", "POST",
                     "business_rule", "to_account", "400 for same account"),
        ],
        "document": [
            Invariant("", "Document access respects org boundaries", "", "GET",
                     "multi_tenancy", "org_id", "403 for cross-org access"),
        ],
        "status": [
            Invariant("", "Status transitions follow defined order", "", "PUT",
                     "state_machine", "status", "400 for invalid transitions"),
        ],
    }

    def discover(self, endpoints: List[dict], code_analysis: dict = None) -> List[Invariant]:
        """
        Discover invariants from API endpoints.

        Args:
            endpoints: list of {"method": "GET", "path": "/api/users/{id}", "auth": True}
            code_analysis: optional code analysis results for deeper invariant discovery
        """
        invariants = []
        inv_id = 0

        for ep in endpoints:
            path = ep.get("path", "").lower()
            method = ep.get("method", "GET").upper()

            for pattern_key, pattern_invariants in self.ENDPOINT_PATTERNS.items():
                if pattern_key in path:
                    for inv_template in pattern_invariants:
                        inv_id += 1
                        inv = Invariant(
                            id=f"inv_{inv_id}",
                            description=inv_template.description,
                            endpoint=ep.get("path", ""),
                            method=method,
                            invariant_type=inv_template.invariant_type,
                            check_field=inv_template.check_field,
                            expected_behavior=inv_template.expected_behavior,
                            confidence=0.6,
                        )
                        invariants.append(inv)

        # Generic invariants (always test)
        generic = [
            Invariant(f"inv_{inv_id+1}", "API responses should not leak internal IDs",
                     "", "GET", "information_disclosure", "", "No internal IDs in response"),
            Invariant(f"inv_{inv_id+2}", "Rate limiting should be enforced on auth endpoints",
                     "", "POST", "rate_limiting", "", "429 after excessive requests"),
        ]
        invariants.extend(generic)

        return invariants


class FuzzerGenerator:
    """Phase 2: Generate targeted test scenarios for each invariant."""

    def generate(self, invariants: List[Invariant], auth_tokens: dict = None) -> List[Fuzzer]:
        """Generate fuzzers for each invariant."""
        fuzzers = []
        fuzzer_id = 0
        tokens = auth_tokens or {}

        for inv in invariants:
            fuzzer_id += 1

            if inv.invariant_type == "authorization":
                # Try accessing with different user token
                fuzzers.append(Fuzzer(
                    id=f"fuzz_{fuzzer_id}",
                    invariant_id=inv.id,
                    description=f"Authorization test: {inv.description}",
                    request_method=inv.method,
                    request_url=inv.endpoint,
                    request_headers={"Authorization": f"Bearer {tokens.get('other_user', 'OTHER_TOKEN')}"},
                    expected_status=403,
                    expected_behavior=inv.expected_behavior,
                ))

            elif inv.invariant_type == "multi_tenancy":
                fuzzers.append(Fuzzer(
                    id=f"fuzz_{fuzzer_id}",
                    invariant_id=inv.id,
                    description=f"Cross-tenant test: {inv.description}",
                    request_method=inv.method,
                    request_url=inv.endpoint,
                    request_headers={"Authorization": f"Bearer {tokens.get('other_org', 'OTHER_ORG_TOKEN')}"},
                    expected_status=403,
                    expected_behavior=inv.expected_behavior,
                ))

            elif inv.invariant_type == "business_rule":
                if inv.check_field == "amount":
                    fuzzers.append(Fuzzer(
                        id=f"fuzz_{fuzzer_id}",
                        invariant_id=inv.id,
                        description=f"Negative amount test: {inv.description}",
                        request_method="POST",
                        request_url=inv.endpoint,
                        request_body={inv.check_field: -100},
                        request_headers={"Content-Type": "application/json"},
                        expected_status=400,
                        expected_behavior="Reject negative amounts",
                    ))
                elif inv.check_field == "to_account":
                    fuzzers.append(Fuzzer(
                        id=f"fuzz_{fuzzer_id}",
                        invariant_id=inv.id,
                        description=f"Same-account test: {inv.description}",
                        request_method="POST",
                        request_url=inv.endpoint,
                        request_body={"from": "ACC1", "to_account": "ACC1", "amount": 10},
                        request_headers={"Content-Type": "application/json"},
                        expected_status=400,
                        expected_behavior="Reject same-account transfers",
                    ))

            elif inv.invariant_type == "state_machine":
                fuzzers.append(Fuzzer(
                    id=f"fuzz_{fuzzer_id}",
                    invariant_id=inv.id,
                    description=f"Skip state test: {inv.description}",
                    request_method="PUT",
                    request_url=inv.endpoint,
                    request_body={"status": "approved"},  # Skip intermediate steps
                    request_headers={"Content-Type": "application/json"},
                    expected_status=400,
                    expected_behavior="Reject invalid state transitions",
                ))

        return fuzzers


class ViolationDetector:
    """Phase 3: Execute fuzzers and detect violations."""

    def detect(self, fuzzers: List[Fuzzer], timeout: int = 10) -> List[Violation]:
        """Execute fuzzers and detect invariant violations."""
        violations = []

        for fuzzer in fuzzers:
            try:
                if fuzzer.request_method == "GET":
                    resp = requests.get(
                        fuzzer.request_url,
                        headers=fuzzer.request_headers,
                        timeout=timeout,
                        allow_redirects=False,
                    )
                elif fuzzer.request_method == "POST":
                    resp = requests.post(
                        fuzzer.request_url,
                        headers=fuzzer.request_headers,
                        json=fuzzer.request_body,
                        timeout=timeout,
                        allow_redirects=False,
                    )
                elif fuzzer.request_method == "PUT":
                    resp = requests.put(
                        fuzzer.request_url,
                        headers=fuzzer.request_headers,
                        json=fuzzer.request_body,
                        timeout=timeout,
                        allow_redirects=False,
                    )
                else:
                    continue

                # Check for violation
                if self._is_violation(resp, fuzzer):
                    # Find the invariant
                    inv = Invariant(
                        id=fuzzer.invariant_id,
                        description=fuzzer.description,
                        endpoint=fuzzer.request_url,
                        method=fuzzer.request_method,
                        invariant_type="unknown",
                    )
                    violations.append(Violation(
                        invariant=inv,
                        fuzzer=fuzzer,
                        actual_status=resp.status_code,
                        actual_response=resp.text[:500],
                        evidence=f"Expected {fuzzer.expected_status}, got {resp.status_code}",
                    ))

            except requests.Timeout:
                logger.debug(f"Timeout testing {fuzzer.request_url}")
            except Exception as e:
                logger.debug(f"Error testing {fuzzer.request_url}: {e}")

        return violations

    def _is_violation(self, response: requests.Response, fuzzer: Fuzzer) -> bool:
        """Determine if a response indicates an invariant violation."""
        # If we expected 403 but got 200 → violation
        if fuzzer.expected_status == 403 and response.status_code == 200:
            return True
        # If we expected 400 but got 200 → violation
        if fuzzer.expected_status == 400 and response.status_code == 200:
            return True
        # If we expected 429 but got 200 → possible violation
        if fuzzer.expected_status == 429 and response.status_code == 200:
            return True
        return False


class ExploitSynthesizer:
    """Phase 4: Generate PoC exploits from violations."""

    def synthesize(self, violation: Violation) -> dict:
        """Generate a complete PoC from a violation."""
        return violation.to_finding()


class BusinessLogicTester:
    """
    Orchestrates the 4-phase business logic testing pipeline.

    Usage:
        tester = BusinessLogicTester()
        results = tester.test(
            endpoints=[{"method": "GET", "path": "/api/users/{id}"}],
            auth_tokens={"other_user": "token123"},
            target="http://localhost:3000"
        )
    """

    def __init__(self):
        self.discoverer = InvariantDiscoverer()
        self.fuzzer_gen = FuzzerGenerator()
        self.detector = ViolationDetector()
        self.synthesizer = ExploitSynthesizer()

    def test(self, endpoints: List[dict] = None, auth_tokens: dict = None,
             target: str = "", timeout: int = 10) -> List[dict]:
        """
        Run the full 4-phase pipeline.

        Returns list of findings (dicts ready for findings bus).
        """
        start = time.time()

        # ── Authorization gate ──
        from cyber.authorization import require_authorization, AuthorizationError
        auth_target = target or (endpoints[0].get("url", "") if endpoints else "")
        if auth_target:
            try:
                require_authorization(auth_target, "business_logic")
            except AuthorizationError as e:
                logger.warning(f"[BizLogic] Authorization denied: {e}")
                return []

        # Default endpoints if none provided
        if not endpoints:
            endpoints = self._discover_endpoints(target)

        # Phase 1: Discover invariants
        invariants = self.discoverer.discover(endpoints)
        logger.info(f"[BizLogic] Discovered {len(invariants)} invariants")

        # Phase 2: Generate fuzzers
        fuzzers = self.fuzzer_gen.generate(invariants, auth_tokens)
        logger.info(f"[BizLogic] Generated {len(fuzzers)} fuzzers")

        # Phase 3: Detect violations
        violations = self.detector.detect(fuzzers, timeout)
        logger.info(f"[BizLogic] Found {len(violations)} violations")

        # Phase 4: Synthesize exploits
        findings = []
        for violation in violations:
            finding = self.synthesizer.synthesize(violation)
            findings.append(finding)

        elapsed = (time.time() - start) * 1000
        logger.info(f"[BizLogic] Complete: {len(findings)} findings in {elapsed:.0f}ms")

        return findings

    def _discover_endpoints(self, target: str) -> List[dict]:
        """Try to discover API endpoints from the target."""
        endpoints = []
        common_paths = [
            "/api/users", "/api/users/{id}", "/api/orders", "/api/orders/{id}",
            "/api/documents", "/api/documents/{id}", "/api/admin", "/api/transfer",
            "/api/profile", "/api/settings", "/api/auth/login", "/api/auth/register",
        ]
        for path in common_paths:
            url = target.rstrip("/") + path.replace("{id}", "1")
            try:
                resp = requests.get(url, timeout=5, allow_redirects=False)
                if resp.status_code not in (404, 405):
                    endpoints.append({"method": "GET", "path": path, "url": url})
            except Exception:
                continue
        return endpoints
