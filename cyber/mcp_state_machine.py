"""
mcp_state_machine.py — Central FSM controller for FRIDAY cyber assessment pipeline.

All state transitions go through typed tools. Single source of truth.
Persists session state to JSON. Exposes JSON-RPC tool interface matching
the existing mcp_server.py pattern.

States: IDLE → RECON → HUNT → CHAIN → VERIFY → GRADE → REPORT → COMPLETE
"""

import json
import sys
import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("friday.cyber.fsm")

# ── Constants ──────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "data" / "cyber_sessions"

VALID_TRANSITIONS: dict[str, list[str]] = {
    "IDLE":     ["RECON"],
    "RECON":    ["HUNT", "IDLE"],
    "HUNT":     ["CHAIN", "RECON", "IDLE"],
    "CHAIN":    ["VERIFY", "HUNT", "IDLE"],
    "VERIFY":   ["GRADE", "CHAIN", "HUNT", "IDLE"],
    "GRADE":    ["REPORT", "VERIFY", "IDLE"],
    "REPORT":   ["COMPLETE", "GRADE", "IDLE"],
    "COMPLETE": ["IDLE"],
    "PAUSED":   ["RECON", "HUNT", "CHAIN", "VERIFY", "GRADE", "REPORT"],
}


# ── Session Model ─────────────────────────────────────────────────

class SessionManager:
    """Manages cyber assessment session lifecycle and persistence."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or SESSIONS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("..", "_")
        return self.base_dir / safe / "session.json"

    def _session_dir(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("..", "_")
        d = self.base_dir / safe
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(self, session_id: str, target: str, mode: str = "standard",
               metadata: Optional[dict] = None) -> dict:
        """Create a new cyber assessment session."""
        p = self._session_path(session_id)
        if p.exists():
            raise ValueError(f"Session already exists: {session_id}")

        now = datetime.now(timezone.utc).isoformat()
        session = {
            "session_id": session_id,
            "target": target,
            "mode": mode,
            "state": "IDLE",
            "previous_state": None,
            "created_at": now,
            "updated_at": now,
            "phase_history": [],
            "findings_count": 0,
            "next_finding_seq": 1,
            "waves": {},
            "metadata": metadata or {},
            "paused": False,
        }
        self._save(session_id, session)
        logger.info("Session created: %s target=%s mode=%s", session_id, target, mode)
        return session

    def read(self, session_id: str) -> dict:
        """Read current session state."""
        p = self._session_path(session_id)
        if not p.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    def update(self, session_id: str, **fields) -> dict:
        """Update arbitrary session fields."""
        session = self.read(session_id)
        for k, v in fields.items():
            if k in ("session_id", "created_at"):
                continue  # immutable
            session[k] = v
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(session_id, session)
        return session

    def transition(self, session_id: str, new_state: str) -> dict:
        """Transition session to a new state with validation."""
        session = self.read(session_id)
        current = session["state"]

        if current == "PAUSED":
            allowed = VALID_TRANSITIONS.get("PAUSED", [])
        else:
            allowed = VALID_TRANSITIONS.get(current, [])

        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {current} → {new_state}. "
                f"Allowed: {allowed}"
            )

        session["previous_state"] = current
        session["state"] = new_state
        session["paused"] = False
        session["phase_history"].append({
            "from": current,
            "to": new_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(session_id, session)
        logger.info("Transition: %s %s → %s", session_id, current, new_state)
        return session

    def pause(self, session_id: str) -> dict:
        """Pause the session (saves current state)."""
        session = self.read(session_id)
        session["paused"] = True
        session["previous_state"] = session["state"]
        session["state"] = "PAUSED"
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(session_id, session)
        logger.info("Session paused: %s", session_id)
        return session

    def resume(self, session_id: str) -> dict:
        """Resume a paused session to its previous state."""
        session = self.read(session_id)
        if not session.get("paused"):
            raise ValueError(f"Session is not paused: {session_id}")
        restore = session.get("previous_state", "IDLE")
        session["state"] = restore
        session["paused"] = False
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(session_id, session)
        logger.info("Session resumed: %s → %s", session_id, restore)
        return session

    def list_sessions(self) -> list[dict]:
        """List all sessions (lightweight summary)."""
        sessions = []
        for d in self.base_dir.iterdir():
            p = d / "session.json"
            if p.exists():
                try:
                    s = json.loads(p.read_text(encoding="utf-8"))
                    sessions.append({
                        "session_id": s["session_id"],
                        "target": s["target"],
                        "state": s["state"],
                        "mode": s["mode"],
                        "findings_count": s.get("findings_count", 0),
                        "updated_at": s.get("updated_at", ""),
                    })
                except (json.JSONDecodeError, KeyError):
                    continue
        return sessions

    def _save(self, session_id: str, session: dict):
        d = self._session_dir(session_id)
        p = d / "session.json"
        p.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Finding CRUD ──────────────────────────────────────────────────

class FindingStore:
    """CRUD for findings within a session. Canonical IDs: F-1, F-2, ..."""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr

    def _findings_path(self, session_id: str) -> Path:
        return self.session_mgr._session_dir(session_id) / "findings.json"

    def _load(self, session_id: str) -> list[dict]:
        p = self._findings_path(session_id)
        if not p.exists():
            return []
        return json.loads(p.read_text(encoding="utf-8"))

    def _save(self, session_id: str, findings: list[dict]):
        p = self._findings_path(session_id)
        p.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, session_id: str, vuln_class: str, summary: str,
               detail: str = "", file_path: str = "", cvss_score: float = 0.0,
               confidence: str = "plausible", agent: str = "",
               surface_id: str = "", metadata: Optional[dict] = None) -> dict:
        """Record a new finding with canonical ID."""
        session = self.session_mgr.read(session_id)
        seq = session["next_finding_seq"]
        finding_id = f"F-{seq}"

        finding = {
            "finding_id": finding_id,
            "vuln_class": vuln_class,
            "summary": summary,
            "detail": detail,
            "file_path": file_path,
            "cvss_score": cvss_score,
            "confidence": confidence,
            "agent": agent,
            "surface_id": surface_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "verification_rounds": [],
            "grade": None,
            "metadata": metadata or {},
        }

        findings = self._load(session_id)
        findings.append(finding)
        self._save(session_id, findings)

        session["findings_count"] = len(findings)
        session["next_finding_seq"] = seq + 1
        self.session_mgr.update(session_id,
                                findings_count=len(findings),
                                next_finding_seq=seq + 1)

        logger.info("Finding recorded: %s/%s (%s)", session_id, finding_id, vuln_class)
        return finding

    def read(self, session_id: str, finding_id: str) -> dict:
        """Read a single finding by canonical ID."""
        for f in self._load(session_id):
            if f["finding_id"] == finding_id:
                return f
        raise FileNotFoundError(f"Finding not found: {finding_id}")

    def list_all(self, session_id: str, filters: Optional[dict] = None) -> list[dict]:
        """List all findings, optionally filtered."""
        findings = self._load(session_id)
        if not filters:
            return findings
        result = []
        for f in findings:
            match = True
            for k, v in filters.items():
                if f.get(k) != v:
                    match = False
                    break
            if match:
                result.append(f)
        return result

    def update(self, session_id: str, finding_id: str, **fields) -> dict:
        """Update fields on an existing finding."""
        findings = self._load(session_id)
        for f in findings:
            if f["finding_id"] == finding_id:
                for k, v in fields.items():
                    if k == "finding_id":
                        continue
                    f[k] = v
                self._save(session_id, findings)
                return f
        raise FileNotFoundError(f"Finding not found: {finding_id}")


# ── Verification Tracking ─────────────────────────────────────────

class VerificationStore:
    """Tracks verification rounds per finding."""

    def __init__(self, finding_store: FindingStore):
        self.finding_store = finding_store

    def write_round(self, session_id: str, finding_id: str,
                    method: str, result: str, evidence: str = "",
                    confidence_delta: float = 0.0) -> dict:
        """Record a verification round for a finding."""
        finding = self.finding_store.read(session_id, finding_id)
        vround = {
            "round": len(finding["verification_rounds"]) + 1,
            "method": method,
            "result": result,  # "confirmed", "inconclusive", "refuted"
            "evidence": evidence,
            "confidence_delta": confidence_delta,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        finding["verification_rounds"].append(vround)
        self.finding_store.update(session_id, finding_id,
                                  verification_rounds=finding["verification_rounds"])
        logger.info("Verification round %d for %s/%s: %s",
                     vround["round"], session_id, finding_id, result)
        return vround

    def read(self, session_id: str, finding_id: str) -> list[dict]:
        """Read all verification rounds for a finding."""
        finding = self.finding_store.read(session_id, finding_id)
        return finding.get("verification_rounds", [])


# ── Grade Tracking ────────────────────────────────────────────────

class GradeStore:
    """Tracks grade verdicts for findings."""

    def __init__(self, finding_store: FindingStore):
        self.finding_store = finding_store

    def write(self, session_id: str, finding_id: str,
              verdict: str, severity: str = "",
              cvss_override: Optional[float] = None,
              rationale: str = "") -> dict:
        """Write a grade verdict for a finding."""
        grade = {
            "verdict": verdict,  # "critical", "high", "medium", "low", "informational", "false_positive"
            "severity": severity or verdict,
            "cvss_override": cvss_override,
            "rationale": rationale,
            "graded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.finding_store.update(session_id, finding_id, grade=grade)
        logger.info("Grade for %s/%s: %s", session_id, finding_id, verdict)
        return grade

    def read(self, session_id: str, finding_id: str) -> Optional[dict]:
        """Read the grade for a finding."""
        finding = self.finding_store.read(session_id, finding_id)
        return finding.get("grade")


# ── Wave Assignment ───────────────────────────────────────────────

class WaveStore:
    """Manages wave assignments within a session."""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr

    def assign(self, session_id: str, wave_id: int,
               surface_ids: list[str], agent_id: str = "") -> dict:
        """Assign surface_ids to a wave."""
        session = self.session_mgr.read(session_id)
        wave_key = f"wave-{wave_id}"
        wave = {
            "wave_id": wave_id,
            "surface_ids": surface_ids,
            "agent_id": agent_id,
            "status": "pending",
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "findings": [],
        }
        session["waves"][wave_key] = wave
        self.session_mgr.update(session_id, waves=session["waves"])

        # Also persist to dedicated file
        d = self.session_mgr._session_dir(session_id)
        wave_file = d / f"wave-{wave_id}-assignments.json"
        wave_file.write_text(json.dumps(wave, indent=2), encoding="utf-8")

        logger.info("Wave %d assigned in %s: %d surface_ids",
                     wave_id, session_id, len(surface_ids))
        return wave

    def merge(self, session_id: str, wave_id: int,
              findings: list[str], status: str = "completed") -> dict:
        """Merge results from a completed wave."""
        session = self.session_mgr.read(session_id)
        wave_key = f"wave-{wave_id}"
        if wave_key not in session["waves"]:
            raise ValueError(f"Wave not found: {wave_key}")

        wave = session["waves"][wave_key]
        wave["status"] = status
        wave["findings"] = findings
        wave["completed_at"] = datetime.now(timezone.utc).isoformat()
        session["waves"][wave_key] = wave
        self.session_mgr.update(session_id, waves=session["waves"])
        logger.info("Wave %d merged in %s: status=%s findings=%d",
                     wave_id, session_id, status, len(findings))
        return wave

    def get_assigned_surface_ids(self, session_id: str) -> set[str]:
        """Get all surface_ids already assigned across all waves (dedup)."""
        session = self.session_mgr.read(session_id)
        assigned = set()
        for wave in session.get("waves", {}).values():
            assigned.update(wave.get("surface_ids", []))
        return assigned


# ── Dead-End Logging ──────────────────────────────────────────────

class DeadEndStore:
    """Logs dead-end (tested-and-failed) approaches within a session."""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr

    def _dead_ends_path(self, session_id: str) -> Path:
        return self.session_mgr._session_dir(session_id) / "dead_ends.jsonl"

    def log(self, session_id: str, target: str, attack_vector: str,
            surface_id: str, reason: str) -> dict:
        """Log a dead-end approach."""
        entry = {
            "target": target,
            "attack_vector": attack_vector,
            "surface_id": surface_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        p = self._dead_ends_path(session_id)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Dead end logged: %s %s/%s", session_id, attack_vector, surface_id)
        return entry

    def read_all(self, session_id: str) -> list[dict]:
        """Read all dead-end entries."""
        p = self._dead_ends_path(session_id)
        if not p.exists():
            return []
        entries = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def is_dead_end(self, session_id: str, target: str,
                    attack_vector: str, surface_id: str) -> bool:
        """Check if this target+vector+surface has already been tested and failed."""
        for entry in self.read_all(session_id):
            if (entry.get("target") == target and
                entry.get("attack_vector") == attack_vector and
                entry.get("surface_id") == surface_id):
                return True
        return False


# ── JSON-RPC Tool Interface ───────────────────────────────────────

_session_mgr = SessionManager()
_finding_store = FindingStore(_session_mgr)
_verification_store = VerificationStore(_finding_store)
_grade_store = GradeStore(_finding_store)
_wave_store = WaveStore(_session_mgr)
_dead_end_store = DeadEndStore(_session_mgr)


def _handle_tool(name: str, params: dict) -> dict:
    """Route a tool call to the appropriate handler."""
    try:
        if name == "cyber_init_session":
            return _session_mgr.create(
                session_id=params["session_id"],
                target=params["target"],
                mode=params.get("mode", "standard"),
                metadata=params.get("metadata"),
            )

        elif name == "cyber_transition_phase":
            return _session_mgr.transition(
                session_id=params["session_id"],
                new_state=params["new_state"],
            )

        elif name == "cyber_record_finding":
            return _finding_store.record(
                session_id=params["session_id"],
                vuln_class=params["vuln_class"],
                summary=params["summary"],
                detail=params.get("detail", ""),
                file_path=params.get("file_path", ""),
                cvss_score=params.get("cvss_score", 0.0),
                confidence=params.get("confidence", "plausible"),
                agent=params.get("agent", ""),
                surface_id=params.get("surface_id", ""),
                metadata=params.get("metadata"),
            )

        elif name == "cyber_read_findings":
            return {"findings": _finding_store.list_all(
                session_id=params["session_id"],
                filters=params.get("filters"),
            )}

        elif name == "cyber_list_findings":
            findings = _finding_store.list_all(
                session_id=params["session_id"],
                filters=params.get("filters"),
            )
            return {"findings": [
                {"finding_id": f["finding_id"],
                 "vuln_class": f["vuln_class"],
                 "confidence": f["confidence"],
                 "cvss_score": f["cvss_score"],
                 "summary": f["summary"][:120]}
                for f in findings
            ]}

        elif name == "cyber_write_verification":
            return _verification_store.write_round(
                session_id=params["session_id"],
                finding_id=params["finding_id"],
                method=params["method"],
                result=params["result"],
                evidence=params.get("evidence", ""),
                confidence_delta=params.get("confidence_delta", 0.0),
            )

        elif name == "cyber_read_verification":
            return {"verification_rounds": _verification_store.read(
                session_id=params["session_id"],
                finding_id=params["finding_id"],
            )}

        elif name == "cyber_write_grade":
            return _grade_store.write(
                session_id=params["session_id"],
                finding_id=params["finding_id"],
                verdict=params["verdict"],
                severity=params.get("severity", ""),
                cvss_override=params.get("cvss_override"),
                rationale=params.get("rationale", ""),
            )

        elif name == "cyber_read_grade":
            grade = _grade_store.read(
                session_id=params["session_id"],
                finding_id=params["finding_id"],
            )
            return {"grade": grade}

        elif name == "cyber_assign_wave":
            return _wave_store.assign(
                session_id=params["session_id"],
                wave_id=params["wave_id"],
                surface_ids=params["surface_ids"],
                agent_id=params.get("agent_id", ""),
            )

        elif name == "cyber_merge_wave":
            return _wave_store.merge(
                session_id=params["session_id"],
                wave_id=params["wave_id"],
                findings=params.get("findings", []),
                status=params.get("status", "completed"),
            )

        elif name == "cyber_log_dead_end":
            return _dead_end_store.log(
                session_id=params["session_id"],
                target=params["target"],
                attack_vector=params["attack_vector"],
                surface_id=params["surface_id"],
                reason=params["reason"],
            )

        elif name == "cyber_read_dead_ends":
            return {"dead_ends": _dead_end_store.read_all(
                session_id=params["session_id"],
            )}

        elif name == "cyber_session_state":
            session = _session_mgr.read(params["session_id"])
            findings = _finding_store.list_all(params["session_id"])
            dead_ends = _dead_end_store.read_all(params["session_id"])
            return {
                "session": session,
                "findings_count": len(findings),
                "dead_ends_count": len(dead_ends),
                "waves_summary": {
                    k: {"status": v["status"],
                        "surface_count": len(v.get("surface_ids", [])),
                        "findings_count": len(v.get("findings", []))}
                    for k, v in session.get("waves", {}).items()
                },
            }

        else:
            return {"error": f"Unknown tool: {name}"}

    except FileNotFoundError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    except KeyError as e:
        return {"error": f"Missing required parameter: {e}"}
    except Exception as e:
        logger.exception("Tool error: %s", name)
        return {"error": f"Internal error: {e}"}


# ── JSON-RPC Server ───────────────────────────────────────────────

TOOL_NAMES = [
    "cyber_init_session",
    "cyber_transition_phase",
    "cyber_record_finding",
    "cyber_read_findings",
    "cyber_list_findings",
    "cyber_write_verification",
    "cyber_read_verification",
    "cyber_write_grade",
    "cyber_read_grade",
    "cyber_assign_wave",
    "cyber_merge_wave",
    "cyber_log_dead_end",
    "cyber_read_dead_ends",
    "cyber_session_state",
]


async def handle_request(request: dict) -> dict:
    """Process a JSON-RPC request and return response."""
    req_id = request.get("id", 0)
    method = request.get("method", "")
    params = request.get("params", {})

    if method not in TOOL_NAMES:
        return {
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _handle_tool, method, params)
        return {"id": req_id, "result": result}
    except Exception as e:
        return {"id": req_id, "error": {"code": -32000, "message": str(e)}}


async def main_loop():
    """Main FSM server loop — JSON-RPC over stdin/stdout."""
    startup = json.dumps({
        "id": 0,
        "result": {
            "status": "started",
            "server": "friday-cyber-fsm",
            "version": "1.0.0",
            "tools": TOOL_NAMES,
        },
    })
    print(startup)
    sys.stdout.flush()

    loop = asyncio.get_running_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                print(json.dumps({
                    "id": 0,
                    "error": {"code": -32700, "message": "Parse error"},
                }))
                sys.stdout.flush()
                continue

            if not isinstance(request, dict):
                print(json.dumps({
                    "id": 0,
                    "error": {"code": -32600, "message": "Invalid request: not an object"},
                }))
                sys.stdout.flush()
                continue

            response = await handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(json.dumps({
                "id": 0,
                "error": {"code": -32000, "message": f"Server error: {e}"},
            }))
            sys.stdout.flush()

    print(json.dumps({
        "id": 0,
        "result": {"status": "shutdown", "server": "friday-cyber-fsm"},
    }))
    sys.stdout.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(main_loop())
