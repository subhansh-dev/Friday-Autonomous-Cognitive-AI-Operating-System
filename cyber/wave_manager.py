"""
wave_manager.py — Parallel wave coordination for FRIDAY cyber assessments.

Splits attack surface into waves, assigns surface_ids to prevent double-testing,
tracks wave status, and merges results from completed waves.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("friday.cyber.waves")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "cyber_sessions"

DEFAULT_WAVE_SIZE = 5
MAX_CONCURRENCY = 10
MIN_CONCURRENCY = 1


class WaveManager:
    """Coordinates parallel attack surface testing in waves."""

    def __init__(self, session_dir: Path, wave_size: int = DEFAULT_WAVE_SIZE,
                 concurrency: int = 3):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.wave_size = max(1, wave_size)
        self.concurrency = max(MIN_CONCURRENCY, min(MAX_CONCURRENCY, concurrency))

    def _wave_file(self, wave_id: int) -> Path:
        return self.session_dir / f"wave-{wave_id}-assignments.json"

    def _status_file(self) -> Path:
        return self.session_dir / "wave_status.json"

    def _load_status(self) -> dict:
        p = self._status_file()
        if not p.exists():
            return {"waves": {}, "total_surface_ids": 0, "tested_surface_ids": []}
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_status(self, status: dict):
        p = self._status_file()
        p.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")

    def split_surface(self, surface_ids: list[str]) -> list[list[str]]:
        """Split a full attack surface into wave-sized chunks."""
        # Deduplicate input
        unique = list(dict.fromkeys(surface_ids))
        waves = []
        for i in range(0, len(unique), self.wave_size):
            waves.append(unique[i:i + self.wave_size])
        return waves

    def assign_waves(self, surface_ids: list[str],
                     agent_ids: Optional[list[str]] = None) -> list[dict]:
        """Assign surface_ids to waves, skipping already-tested ones."""
        status = self._load_status()
        already_tested = set(status.get("tested_surface_ids", []))

        # Filter out already tested
        fresh = [sid for sid in surface_ids if sid not in already_tested]
        skipped = len(surface_ids) - len(fresh)

        if skipped > 0:
            logger.info("Skipped %d already-tested surface_ids", skipped)

        chunks = self.split_surface(fresh)
        assignments = []

        for i, chunk in enumerate(chunks):
            wave_id = i + 1
            agent_id = ""
            if agent_ids and i < len(agent_ids):
                agent_id = agent_ids[i % len(agent_ids)]

            wave = {
                "wave_id": wave_id,
                "surface_ids": chunk,
                "agent_id": agent_id,
                "status": "pending",
                "assigned_at": datetime.now(timezone.utc).isoformat(),
                "started_at": None,
                "completed_at": None,
                "duration_s": None,
                "findings": [],
                "error": None,
            }

            # Persist wave assignment file
            self._wave_file(wave_id).write_text(
                json.dumps(wave, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Update status
            status["waves"][f"wave-{wave_id}"] = {
                "status": "pending",
                "surface_count": len(chunk),
                "agent_id": agent_id,
            }
            assignments.append(wave)

        status["total_surface_ids"] = len(surface_ids)
        self._save_status(status)

        logger.info("Assigned %d waves (%d surface_ids, %d skipped)",
                     len(chunks), len(fresh), skipped)
        return assignments

    def mark_running(self, wave_id: int) -> dict:
        """Mark a wave as running."""
        wave = self._read_wave(wave_id)
        wave["status"] = "running"
        wave["started_at"] = datetime.now(timezone.utc).isoformat()
        self._write_wave(wave_id, wave)
        self._update_status_wave(wave_id, "running")
        logger.info("Wave %d marked running", wave_id)
        return wave

    def mark_completed(self, wave_id: int, findings: Optional[list] = None,
                       error: Optional[str] = None) -> dict:
        """Mark a wave as completed (or failed)."""
        wave = self._read_wave(wave_id)
        wave["completed_at"] = datetime.now(timezone.utc).isoformat()

        if wave.get("started_at"):
            try:
                start = datetime.fromisoformat(wave["started_at"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(wave["completed_at"].replace("Z", "+00:00"))
                wave["duration_s"] = (end - start).total_seconds()
            except (ValueError, TypeError):
                pass

        if error:
            wave["status"] = "failed"
            wave["error"] = error
        else:
            wave["status"] = "completed"
            wave["findings"] = findings or []

        self._write_wave(wave_id, wave)
        self._update_status_wave(wave_id, wave["status"])

        # Mark surface_ids as tested
        status = self._load_status()
        tested = set(status.get("tested_surface_ids", []))
        tested.update(wave.get("surface_ids", []))
        status["tested_surface_ids"] = list(tested)
        self._save_status(status)

        logger.info("Wave %d completed: status=%s findings=%d",
                     wave_id, wave["status"], len(wave.get("findings", [])))
        return wave

    def merge_results(self, wave_ids: Optional[list[int]] = None) -> dict:
        """Merge findings from completed waves. If wave_ids is None, merge all."""
        status = self._load_status()
        if wave_ids is None:
            wave_ids = [
                int(k.split("-")[1])
                for k in status.get("waves", {})
                if status["waves"][k].get("status") == "completed"
            ]

        all_findings = []
        merged_waves = []
        errors = []

        for wid in wave_ids:
            try:
                wave = self._read_wave(wid)
                if wave["status"] != "completed":
                    errors.append(f"Wave {wid} not completed (status={wave['status']})")
                    continue
                all_findings.extend(wave.get("findings", []))
                merged_waves.append(wid)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                errors.append(f"Wave {wid}: {e}")

        # Deduplicate findings by finding_id
        seen = set()
        unique_findings = []
        for f in all_findings:
            fid = f.get("finding_id", "") if isinstance(f, dict) else str(f)
            if fid not in seen:
                seen.add(fid)
                unique_findings.append(f)

        result = {
            "merged_waves": merged_waves,
            "total_findings": len(unique_findings),
            "findings": unique_findings,
            "errors": errors,
            "merged_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save merged results
        merged_file = self.session_dir / "merged_results.json"
        merged_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info("Merged %d waves: %d unique findings", len(merged_waves), len(unique_findings))
        return result

    def get_next_pending(self) -> Optional[dict]:
        """Get the next pending wave for execution."""
        status = self._load_status()
        for k, info in sorted(status.get("waves", {}).items()):
            if info.get("status") == "pending":
                wave_id = int(k.split("-")[1])
                return self._read_wave(wave_id)
        return None

    def get_summary(self) -> dict:
        """Get a summary of all waves."""
        status = self._load_status()
        summary = {
            "total_surface_ids": status.get("total_surface_ids", 0),
            "tested_surface_ids": len(status.get("tested_surface_ids", [])),
            "waves": {},
        }
        for k, info in status.get("waves", {}).items():
            summary["waves"][k] = info
        return summary

    def _read_wave(self, wave_id: int) -> dict:
        p = self._wave_file(wave_id)
        if not p.exists():
            raise FileNotFoundError(f"Wave file not found: wave-{wave_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _write_wave(self, wave_id: int, wave: dict):
        p = self._wave_file(wave_id)
        p.write_text(json.dumps(wave, indent=2, ensure_ascii=False), encoding="utf-8")

    def _update_status_wave(self, wave_id: int, wave_status: str):
        status = self._load_status()
        key = f"wave-{wave_id}"
        if key in status.get("waves", {}):
            status["waves"][key]["status"] = wave_status
        self._save_status(status)


def get_wave_manager(session_dir: str | Path,
                     wave_size: int = DEFAULT_WAVE_SIZE,
                     concurrency: int = 3) -> WaveManager:
    """Factory for WaveManager instances."""
    return WaveManager(Path(session_dir), wave_size, concurrency)
