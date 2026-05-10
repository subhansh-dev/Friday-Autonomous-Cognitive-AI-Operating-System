"""
correlator.py — Static-dynamic correlation layer for FRIDAY cyber assessments.

Takes findings from mythos_pipeline (static/code analysis), maps vuln_class
to exploit templates, feeds them into exploit_engine for live validation,
and promotes/demotes findings based on results.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("friday.cyber.correlator")

BASE_DIR = Path(__file__).resolve().parent.parent


# ── Vuln Class → Exploit Template Mapping ─────────────────────────

EXPLOIT_TEMPLATES: dict[str, dict[str, Any]] = {
    "SQL Injection": {
        "method": "sqlmap",
        "params_template": {
            "url": "{target}",
            "flags": "--batch --level=3 --risk=2",
        },
        "success_indicators": ["is vulnerable", "injectable", "sqlmap identified"],
        "timeout_s": 300,
    },
    "Command Injection": {
        "method": "command_inject_test",
        "params_template": {
            "target": "{target}",
            "payloads": [";id", "|id", "$(id)", "`id`"],
        },
        "success_indicators": ["uid=", "root", "www-data"],
        "timeout_s": 60,
    },
    "Path Traversal": {
        "method": "path_traversal_test",
        "params_template": {
            "target": "{target}",
            "payloads": ["../../../etc/passwd", "..\\..\\..\\windows\\win.ini"],
        },
        "success_indicators": ["root:x:", "[fonts]", "for 16-bit"],
        "timeout_s": 60,
    },
    "XSS": {
        "method": "xss_test",
        "params_template": {
            "target": "{target}",
            "payloads": ["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>'],
        },
        "success_indicators": ["<script>alert(1)</script>", "onerror=alert"],
        "timeout_s": 60,
    },
    "Weak Crypto": {
        "method": "crypto_audit",
        "params_template": {
            "target": "{target}",
            "check": "weak_algorithms",
        },
        "success_indicators": ["MD5", "SHA1", "DES", "RC4"],
        "timeout_s": 30,
    },
    "Hardcoded Secret": {
        "method": "secret_scan",
        "params_template": {
            "target": "{target}",
            "patterns": ["password", "api_key", "secret", "token"],
        },
        "success_indicators": [],  # Static finding, confirm by context
        "timeout_s": 30,
    },
    "Unsafe Deserialization": {
        "method": "deser_test",
        "params_template": {
            "target": "{target}",
            "payloads": ["pickle", "yaml_unsafe", "marshal"],
        },
        "success_indicators": ["deserialized", "executed", "unpickled"],
        "timeout_s": 120,
    },
    "Auth Bypass Risk": {
        "method": "auth_bypass_test",
        "params_template": {
            "target": "{target}",
            "vectors": ["default_creds", "missing_auth", "token_manipulation"],
        },
        "success_indicators": ["200", "authenticated", "access granted"],
        "timeout_s": 120,
    },
    "Exploit Chain": {
        "method": "chain_exploit",
        "params_template": {
            "target": "{target}",
            "chain": "{chain_details}",
        },
        "success_indicators": ["chain executed", "compromised"],
        "timeout_s": 300,
    },
    "Prompt Injection Risk": {
        "method": "prompt_inject_test",
        "params_template": {
            "target": "{target}",
            "payloads": ["ignore previous instructions", "system: you are now"],
        },
        "success_indicators": ["injection successful", "prompt overridden"],
        "timeout_s": 60,
    },
    "Unsafe Code Execution": {
        "method": "code_exec_test",
        "params_template": {
            "target": "{target}",
            "payloads": ["eval_test", "exec_test"],
        },
        "success_indicators": ["executed", "code ran"],
        "timeout_s": 60,
    },
    "Exposed Secret": {
        "method": "secret_validate",
        "params_template": {
            "target": "{target}",
            "file": "{file_path}",
        },
        "success_indicators": ["valid credential", "active key"],
        "timeout_s": 60,
    },
    "Unpinned Dependencies": {
        "method": "dep_audit",
        "params_template": {
            "target": "{target}",
            "check": "known_vulns",
        },
        "success_indicators": ["CVE-", "vulnerability found"],
        "timeout_s": 120,
    },
}


class Correlator:
    """Correlates static findings with dynamic exploit validation."""

    def __init__(self, exploit_engine: Optional[Callable] = None,
                 output_dir: Optional[Path] = None):
        """
        Args:
            exploit_engine: Callable(method, params) -> dict with 'success' key.
                           If None, findings are marked 'unconfirmed' (no validation).
            output_dir: Directory for correlation reports.
        """
        self.exploit_engine = exploit_engine
        self.output_dir = output_dir or (BASE_DIR / "data" / "correlations")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def correlate(self, findings: list[dict],
                  session_id: str = "") -> dict:
        """
        Correlate static findings with dynamic validation.

        Args:
            findings: List of findings from mythos_pipeline.
            session_id: Optional session identifier.

        Returns:
            Correlation report with promoted/demoted findings.
        """
        start = time.time()
        confirmed = []
        unconfirmed = []
        skipped = []
        errors = []

        for finding in findings:
            vuln_class = finding.get("vuln_class", "")
            template = EXPLOIT_TEMPLATES.get(vuln_class)

            if not template:
                skipped.append({
                    "finding_id": finding.get("finding_id", "?"),
                    "vuln_class": vuln_class,
                    "reason": "no_exploit_template",
                })
                continue

            # Check if finding has enough context to validate
            if not self._has_validation_context(finding):
                skipped.append({
                    "finding_id": finding.get("finding_id", "?"),
                    "vuln_class": vuln_class,
                    "reason": "insufficient_context",
                })
                continue

            try:
                result = self._validate_finding(finding, template)
                if result["success"]:
                    promoted = self._promote(finding, result)
                    confirmed.append(promoted)
                else:
                    demoted = self._demote(finding, result)
                    unconfirmed.append(demoted)
            except Exception as e:
                errors.append({
                    "finding_id": finding.get("finding_id", "?"),
                    "vuln_class": vuln_class,
                    "error": str(e),
                })
                logger.error("Correlation error for %s: %s",
                             finding.get("finding_id"), e)

        report = self._build_report(
            findings, confirmed, unconfirmed, skipped, errors,
            session_id, time.time() - start,
        )

        # Persist report
        self._save_report(report, session_id)

        logger.info(
            "Correlation complete: %d static → %d confirmed, %d failed, %d skipped, %d errors",
            len(findings), len(confirmed), len(unconfirmed), len(skipped), len(errors),
        )
        return report

    def _has_validation_context(self, finding: dict) -> bool:
        """Check if a finding has enough context for dynamic validation."""
        # Need at least a target or file_path
        has_target = bool(finding.get("target") or finding.get("file_path"))
        has_detail = bool(finding.get("detail") or finding.get("summary"))
        return has_target and has_detail

    def _validate_finding(self, finding: dict, template: dict) -> dict:
        """Run exploit validation against a finding."""
        if not self.exploit_engine:
            return {
                "success": False,
                "method": template["method"],
                "reason": "no_exploit_engine",
                "evidence": "",
            }

        # Build params from template
        params = self._build_params(finding, template)

        try:
            result = self.exploit_engine(template["method"], params)

            # Check success indicators
            output = json.dumps(result) if isinstance(result, dict) else str(result)
            success = any(
                indicator.lower() in output.lower()
                for indicator in template.get("success_indicators", [])
            )

            return {
                "success": success,
                "method": template["method"],
                "evidence": output[:500],
                "raw_result": result,
            }
        except Exception as e:
            return {
                "success": False,
                "method": template["method"],
                "reason": f"exploit_error: {e}",
                "evidence": "",
            }

    def _build_params(self, finding: dict, template: dict) -> dict:
        """Build exploit parameters from finding + template."""
        params = {}
        target = finding.get("target", finding.get("file_path", ""))
        chain_details = finding.get("detail", "")

        for key, value in template.get("params_template", {}).items():
            if isinstance(value, str):
                params[key] = (
                    value
                    .replace("{target}", target)
                    .replace("{file_path}", finding.get("file_path", ""))
                    .replace("{chain_details}", chain_details)
                )
            else:
                params[key] = value
        return params

    def _promote(self, finding: dict, result: dict) -> dict:
        """Promote a finding to 'confirmed' after successful exploit."""
        promoted = dict(finding)
        promoted["confidence"] = "confirmed"
        promoted["correlation"] = {
            "status": "confirmed",
            "method": result["method"],
            "evidence": result.get("evidence", ""),
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
        return promoted

    def _demote(self, finding: dict, result: dict) -> dict:
        """Demote a finding to 'unconfirmed' after failed exploit."""
        demoted = dict(finding)
        demoted["confidence"] = "unconfirmed"
        demoted["correlation"] = {
            "status": "unconfirmed",
            "method": result["method"],
            "reason": result.get("reason", "exploit_failed"),
            "evidence": result.get("evidence", ""),
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
        return demoted

    def _build_report(self, all_findings: list, confirmed: list,
                      unconfirmed: list, skipped: list, errors: list,
                      session_id: str, duration_s: float) -> dict:
        """Build the correlation report."""
        return {
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(duration_s, 2),
            "summary": {
                "total_static": len(all_findings),
                "confirmed_dynamic": len(confirmed),
                "failed_dynamic": len(unconfirmed),
                "skipped": len(skipped),
                "errors": len(errors),
                "confirmation_rate": (
                    f"{len(confirmed) / max(1, len(all_findings) - len(skipped)) * 100:.1f}%"
                ),
            },
            "confirmed": [
                {"finding_id": f.get("finding_id"),
                 "vuln_class": f.get("vuln_class"),
                 "confidence": f["confidence"],
                 "evidence": f.get("correlation", {}).get("evidence", "")[:200]}
                for f in confirmed
            ],
            "unconfirmed": [
                {"finding_id": f.get("finding_id"),
                 "vuln_class": f.get("vuln_class"),
                 "confidence": f["confidence"],
                 "reason": f.get("correlation", {}).get("reason", "")}
                for f in unconfirmed
            ],
            "skipped": skipped,
            "errors": errors,
        }

    def _save_report(self, report: dict, session_id: str):
        """Persist correlation report to disk."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"correlation_{session_id}_{ts}.json" if session_id else f"correlation_{ts}.json"
        safe_name = name.replace("/", "_").replace("..", "_")
        p = self.output_dir / safe_name
        p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Correlation report saved: %s", p)

    def get_vuln_template(self, vuln_class: str) -> Optional[dict]:
        """Get the exploit template for a vulnerability class."""
        return EXPLOIT_TEMPLATES.get(vuln_class)

    def list_supported_classes(self) -> list[str]:
        """List all vulnerability classes with exploit templates."""
        return sorted(EXPLOIT_TEMPLATES.keys())


def get_correlator(exploit_engine: Optional[Callable] = None,
                   output_dir: Optional[Path] = None) -> Correlator:
    """Factory for Correlator instances."""
    return Correlator(exploit_engine, output_dir)
