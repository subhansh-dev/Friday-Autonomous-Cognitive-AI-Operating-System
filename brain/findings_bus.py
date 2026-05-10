"""
brain/findings_bus.py — Shared Inter-Agent Communication Bus
JSONL-based persistent log for cross-system findings.
Inspired by mythos-agent/mythos-agent orchestrator pattern.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FINDINGS_PATH = DATA_DIR / "findings.jsonl"


def _compute_finding_id(file_path: str, vuln_class: str, line_range: str) -> str:
    raw = f"{file_path}:{vuln_class}:{line_range}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FindingsBus:
    """JSONL-based persistent findings bus for inter-agent communication."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else FINDINGS_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def write(self, finding: dict) -> bool:
        finding_id = finding.get("finding_id")
        if not finding_id:
            return False

        if self._exists(finding_id):
            self._append_evidence(finding_id, finding)
            return False

        if "timestamp" not in finding:
            finding["timestamp"] = datetime.now(timezone.utc).isoformat()

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(finding, ensure_ascii=False) + "\n")
        return True

    def read(self, filters: Optional[dict] = None) -> list:
        findings = []
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    finding = json.loads(line)
                    if filters and not self._matches(finding, filters):
                        continue
                    findings.append(finding)
                except json.JSONDecodeError:
                    continue
        return findings

    def read_recent(self, hours: int = 24) -> list:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        findings = []
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    finding = json.loads(line)
                    ts = finding.get("timestamp", "")
                    if ts:
                        finding_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if finding_time >= cutoff:
                            findings.append(finding)
                except (json.JSONDecodeError, ValueError):
                    continue
        return findings

    def get_confidence_summary(self) -> dict:
        findings = self.read()
        summary = {"confirmed": 0, "likely": 0, "possible": 0, "dismissed": 0}
        for f in findings:
            conf = f.get("confidence", "possible")
            if conf in summary:
                summary[conf] += 1
        summary["total"] = len(findings)
        return summary

    def prune(self, days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept = []
        removed = 0

        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    finding = json.loads(line)
                    ts = finding.get("timestamp", "")
                    if ts:
                        finding_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if finding_time >= cutoff:
                            kept.append(line)
                        else:
                            removed += 1
                    else:
                        kept.append(line)
                except (json.JSONDecodeError, ValueError):
                    kept.append(line)

        with open(self.path, "w", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")

        return removed

    def _exists(self, finding_id: str) -> bool:
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    finding = json.loads(line.strip())
                    if finding.get("finding_id") == finding_id:
                        return True
                except (json.JSONDecodeError, ValueError):
                    continue
        return False

    def _append_evidence(self, finding_id: str, new_finding: dict):
        lines = []
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    finding = json.loads(line.strip())
                    if finding.get("finding_id") == finding_id:
                        evidence = finding.get("additional_evidence", [])
                        evidence.append({
                            "agent": new_finding.get("agent"),
                            "summary": new_finding.get("summary"),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        finding["additional_evidence"] = evidence
                    lines.append(json.dumps(finding, ensure_ascii=False))
                except (json.JSONDecodeError, ValueError):
                    lines.append(line.strip())

        with open(self.path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

    def _matches(self, finding: dict, filters: dict) -> bool:
        for key, value in filters.items():
            if finding.get(key) != value:
                return False
        return True


_bus_instance: Optional[FindingsBus] = None


def get_findings_bus() -> FindingsBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = FindingsBus()
    return _bus_instance
