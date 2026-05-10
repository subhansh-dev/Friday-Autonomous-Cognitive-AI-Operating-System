# -*- coding: utf-8 -*-
"""
neural_memory.py — FRIDAY Neural Memory Core
Brain-Inspired Persistent Memory System

Architecture inspired by human brain memory mechanisms:
- Hippocampus: rapid encoding of new experiences with context
- Neocortex: structured long-term storage
- Hebbian learning: related memories strengthen together
- Synaptic decay (LTD): strength degrades with time → auto-delete at 72h
- Sleep consolidation: background thread replays & consolidates recent memories
- Pattern completion: retrieve full memory from partial cues
"""

import json
import threading
import time
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, List, Dict
from collections import defaultdict
import os
import sys

# Windows console UTF-8 fix
if sys.platform == "win32":
    try:
        import io
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # [#1] Don't crash if already wrapped


# ─── Configuration ───────────────────────────────────────────────────────────

BRAIN_DIR   = Path(__file__).parent.resolve()
MEMORY_FILE = BRAIN_DIR / "neural_store.json"

# Trace decay: memory strength halves every N hours
STRENGTH_HALF_LIFE_HOURS = 24
MAX_STRENGTH             = 10.0
MIN_STRENGTH             = 0.1
TTL_HOURS                = 72

# Consolidation
CONSOLIDATION_INTERVAL_SECONDS = 300
CONSOLIDATION_AGE_HOURS        = 2

# Context linking
MAX_CONTEXT_LINKS = 10
MAX_CATEGORIES    = 50


# ─── Helper: current time ───────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now()


def _timestamp() -> str:
    return _now().isoformat()


def _hours_since(ts: str) -> float:
    try:
        dt = datetime.fromisoformat(ts)
        return (_now() - dt).total_seconds() / 3600
    except (ValueError, TypeError):  # [#2]
        return TTL_HOURS + 1  # treat bad timestamps as expired


# ─── Memory Strength (Synaptic Weight) ──────────────────────────────────────

def _compute_strength(created: str, last_accessed: str, access_count: int) -> float:
    """
    Compute current synaptic strength based on:
    - Time since creation (decay)
    - Time since last access (disuse accelerates decay)
    - Access count (repetition strengthens)
    """
    hours_since_create = _hours_since(created)
    hours_since_access = _hours_since(last_accessed)

    # Base decay
    decay_factor = math.exp(-hours_since_create / STRENGTH_HALF_LIFE_HOURS)

    # Disuse penalty
    disuse_penalty = 1.0
    if hours_since_access > 12:
        disuse_penalty = math.exp(
            -(hours_since_access - 12) / (STRENGTH_HALF_LIFE_HOURS * 2))

    # Potentiation — logarithmic scaling
    potentiation = 1.0 + math.log2(max(1, access_count) + 1) * 0.3

    raw = MAX_STRENGTH * decay_factor * disuse_penalty * potentiation
    return max(0.0, min(MAX_STRENGTH, round(raw, 4)))


def _is_expired(entry: dict) -> bool:
    """Check if memory has exceeded TTL (72-hour hard limit).
    Creator identity memories are exempt — they should never expire."""
    if (entry.get("category") == "identity"
            and entry.get("key", "").startswith("creator_")):
        return False
    created = entry.get("created", entry.get("updated", _timestamp()))
    return _hours_since(created) >= TTL_HOURS


def _should_prune(entry: dict) -> bool:
    """Check if memory should be pruned.
    Creator identity memories are exempt from pruning."""
    if (entry.get("category") == "identity"
            and entry.get("key", "").startswith("creator_")):
        return False
    if _is_expired(entry):
        return True
    return entry.get("strength", 0.0) < MIN_STRENGTH



# ─── Neural Store ────────────────────────────────────────────────────────────

class NeuralStore:
    """
    Brain-inspired persistent memory store for FRIDAY.

    Structure mirrors the brain's memory architecture:
    - Each memory is a "neuron assembly" with synaptic strength
    - Memories link to related memories (Hebbian assemblies)
    - Categories act like cortical regions
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._consolidation_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dirty = False
        self._data: dict = self._empty_store()
        self._load()
        self._start_consolidation()

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 2,
                "created": _timestamp(),
                "last_consolidation": _timestamp(),
                "total_memories_created": 0,
                "total_memories_pruned": 0,
            },
            "hippocampus": [],
            "neocortex": {},
            "links": [],
        }

    # ── File I/O ─────────────────────────────────────────────────────────────

    def _load(self):
        if not MEMORY_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = MEMORY_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            # Ensure all required keys exist
            defaults = self._empty_store()
            for key in ("neocortex", "hippocampus", "links", "meta"):
                if key not in data:
                    data[key] = defaults[key]
            # Ensure meta has all fields
            for mk, mv in defaults["meta"].items():
                if mk not in data["meta"]:
                    data["meta"][mk] = mv
            self._data = data
        except json.JSONDecodeError as e:
            print(f"[Brain] !! Corrupted store: {e}. Backing up and starting fresh.")
            self._backup_corrupted()  # [#3]
            self._data = self._empty_store()
            self._save()
        except IOError as e:
            print(f"[Brain] !! Load error: {e}. Starting fresh.")
            self._data = self._empty_store()
            self._save()

    def _backup_corrupted(self):  # [#3]
        """Back up corrupted store file."""
        try:
            backup = MEMORY_FILE.with_suffix(".json.corrupt")
            MEMORY_FILE.rename(backup)
            print(f"[Brain] Corrupted file backed up to {backup.name}")
        except Exception:
            pass

    def _save(self):
        """Atomic save — write to temp then rename."""  # [#4]
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = MEMORY_FILE.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(MEMORY_FILE)
            self._dirty = False
        except Exception as e:
            print(f"[Brain] !! Save error: {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _save_async(self):
        self._dirty = True

    # ── Core Operations ──────────────────────────────────────────────────────

    def encode(
        self,
        category: str,
        key: str,
        value: str,
        context: Optional[dict] = None,
        link_keys: Optional[list] = None,
    ) -> str:
        """
        Encode a new memory.
        Returns the memory_id.
        """
        # Sanitize inputs [#5]
        category = str(category).strip().lower().replace(" ", "_")
        key = str(key).strip().lower().replace(" ", "_")
        value = str(value).strip()

        if not key or not value:
            return ""

        memory_id = f"{category}:{key}"
        now_ts = _timestamp()

        with self._lock:
            if category not in self._data["neocortex"]:
                if len(self._data["neocortex"]) >= MAX_CATEGORIES:
                    self._prune_weakest_category()
                self._data["neocortex"][category] = {}

            # If memory already exists, update instead of overwrite [#6]
            existing = self._data["neocortex"][category].get(key)
            if existing:
                existing["value"] = value
                existing["updated"] = now_ts
                existing["last_accessed"] = now_ts
                existing["access_count"] = existing.get("access_count", 0) + 1
                existing["strength"] = min(
                    MAX_STRENGTH,
                    existing.get("strength", 5) + 1)
                if context:
                    existing.setdefault("context", {}).update(context)
                self._dirty = True
                print(f"[Brain] ^^ Updated: {memory_id} = {value[:50]}")
                return memory_id

            entry = {
                "key":           key,
                "value":         value,
                "category":      category,
                "memory_id":     memory_id,
                "created":       now_ts,
                "updated":       now_ts,
                "last_accessed": now_ts,
                "access_count":  1,
                "strength":      MAX_STRENGTH,
                "context":       context or {},
                "links":         link_keys or [],
                "consolidated":  False,
            }

            self._data["neocortex"][category][key] = entry
            self._data["hippocampus"].append(memory_id)
            self._data["meta"]["total_memories_created"] += 1

            if link_keys:
                self._add_links(memory_id, link_keys)

            self._dirty = True

        print(f"[Brain] ++ Encoded: {memory_id} = {value[:50]}")
        return memory_id

    def recall(self, memory_id: str) -> Optional[dict]:
        """Retrieve a specific memory by ID. Updates strength (LTP)."""
        try:
            category, key = memory_id.split(":", 1)
        except ValueError:
            return None

        with self._lock:
            cat = self._data["neocortex"].get(category, {})
            entry = cat.get(key)
            if entry is None:
                return None

            # LTP: accessing strengthens the memory
            entry["access_count"] = entry.get("access_count", 0) + 1
            entry["last_accessed"] = _timestamp()
            entry["strength"] = _compute_strength(
                entry["created"], entry["last_accessed"],
                entry["access_count"])
            self._dirty = True
            return dict(entry)

    def recall_by_key(self, category: str, key: str) -> Optional[dict]:
        return self.recall(f"{category}:{key}")

    def recall_by_value(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Pattern completion — find memories matching a partial query.
        """
        results = []
        q = query.lower()

        with self._lock:
            for cat_name, cat_data in self._data["neocortex"].items():
                for key, entry in cat_data.items():
                    if _should_prune(entry):
                        continue
                    val = entry.get("value", "").lower()
                    k = entry.get("key", "").lower()
                    # [#7] Score by match quality
                    score = 0
                    if q in k:
                        score = 2  # key match is stronger
                    elif q in val:
                        score = 1
                    if score > 0:
                        e = dict(entry)
                        e["_match_score"] = score
                        results.append(e)

        # Sort by match score first, then strength
        results.sort(
            key=lambda e: (e.get("_match_score", 0),
                           e.get("strength", 0)),
            reverse=True)
        # Clean up internal score field
        for r in results:
            r.pop("_match_score", None)
        return results[:top_k]

    def remember(self, category: str, key: str) -> str:
        """High-level: recall and return value string."""
        entry = self.recall_by_key(category, key)
        if entry:
            return entry.get("value", "")
        return ""

    def update(
        self,
        category: str,
        key: str,
        value: str,
        context: Optional[dict] = None,
    ) -> bool:
        """Update an existing memory."""
        with self._lock:
            cat = self._data["neocortex"].get(category)
            if cat is None or key not in cat:
                return False

            entry = cat[key]
            old_val = entry["value"]
            entry["value"] = str(value).strip()
            entry["updated"] = _timestamp()
            entry["last_accessed"] = _timestamp()
            entry["access_count"] = entry.get("access_count", 0) + 1
            entry["strength"] = min(
                MAX_STRENGTH, entry.get("strength", 5) + 1)
            if context:
                entry.setdefault("context", {}).update(context)
            self._dirty = True

            if old_val != value:
                print(f"[Brain] ^^ Updated: {category}:{key} "
                      f"'{old_val[:30]}' → '{value[:30]}'")
            return True

    def forget(self, category: str, key: str) -> bool:
        """Delete a specific memory."""
        with self._lock:
            cat = self._data["neocortex"].get(category)
            if cat and key in cat:
                del cat[key]
                self._data["meta"]["total_memories_pruned"] += 1
                self._dirty = True
                print(f"[Brain] -- Forgot: {category}:{key}")
                return True
        return False

    # ── Hebbian Linking ──────────────────────────────────────────────────────

    def _add_links(self, memory_id: str, target_ids: list):
        """Create bidirectional Hebbian links."""
        existing_links = {}
        for link in self._data["links"]:
            pair_key = tuple(sorted(link["pair"]))
            existing_links[pair_key] = link

        for target in target_ids:
            target = str(target).strip()
            if not target or target == memory_id:
                continue
            pair = tuple(sorted([memory_id, target]))
            if pair in existing_links:
                existing_links[pair]["strength"] = min(
                    MAX_STRENGTH,
                    existing_links[pair]["strength"] + 1)
                existing_links[pair]["last_activated"] = _timestamp()
            else:
                self._data["links"].append({
                    "pair":            list(pair),
                    "strength":        5.0,
                    "created":         _timestamp(),
                    "last_activated":  _timestamp(),
                })

        # Cap total links
        if len(self._data["links"]) > MAX_CONTEXT_LINKS * 10:
            self._data["links"].sort(
                key=lambda l: l["strength"], reverse=True)
            self._data["links"] = self._data["links"][:MAX_CONTEXT_LINKS * 10]

    def get_related(self, memory_id: str, top_k: int = 3) -> List[dict]:
        """Find related memories via Hebbian links."""
        related_ids = set()
        for link in self._data["links"]:
            if memory_id in link["pair"]:
                other = (link["pair"][0] if link["pair"][1] == memory_id
                         else link["pair"][1])
                related_ids.add(other)

        results = []
        for rid in related_ids:
            parts = rid.split(":", 1)
            if len(parts) != 2:
                continue
            cat, key = parts
            entry = self.recall_by_key(cat, key)
            if entry:
                results.append(entry)

        return results[:top_k]

    # ── Consolidation ────────────────────────────────────────────────────────

    def _consolidate(self):
        """Replay recent memories, compute strengths, prune weak ones."""
        pruned = 0
        strengthened = 0

        with self._lock:
            for cat_name in list(self._data["neocortex"].keys()):
                cat = self._data["neocortex"][cat_name]
                for key in list(cat.keys()):
                    entry = cat[key]

                    entry["strength"] = _compute_strength(
                        entry["created"],
                        entry["last_accessed"],
                        entry.get("access_count", 1))

                    if _should_prune(entry):
                        del cat[key]
                        pruned += 1
                        self._data["meta"]["total_memories_pruned"] += 1
                        continue

                    if (not entry.get("consolidated", False)
                            and _hours_since(entry["created"]) > CONSOLIDATION_AGE_HOURS):
                        entry["consolidated"] = True
                        strengthened += 1

                # Remove empty categories
                if not cat:
                    del self._data["neocortex"][cat_name]

            # Prune stale hippocampus references
            self._data["hippocampus"] = [
                h for h in self._data["hippocampus"]
                if not self._is_consolidated_or_gone(h)
            ][-200:]

            # Prune stale links [#8]
            self._data["links"] = [
                l for l in self._data["links"]
                if l.get("strength", 0) > MIN_STRENGTH
            ]

            self._data["meta"]["last_consolidation"] = _timestamp()
            self._dirty = True

        if pruned > 0 or strengthened > 0:
            print(f"[Brain] ~~ Consolidation: {strengthened} strengthened, "
                  f"{pruned} pruned")

    def _is_consolidated_or_gone(self, memory_id: str) -> bool:
        try:
            cat, key = memory_id.split(":", 1)
            cat_data = self._data["neocortex"].get(cat, {})
            entry = cat_data.get(key)
            if entry is None:
                return True
            return entry.get("consolidated", False) or _should_prune(entry)
        except (ValueError, KeyError):
            return True

    def _consolidation_loop(self):
        """Background thread: runs consolidation periodically."""
        while not self._stop_event.is_set():
            self._stop_event.wait(CONSOLIDATION_INTERVAL_SECONDS)
            if self._stop_event.is_set():
                break
            try:
                self._consolidate()
                if self._dirty:
                    self._save()
            except Exception as e:
                print(f"[Brain] !! Consolidation error: {e}")

    def _start_consolidation(self):
        if (self._consolidation_thread is None
                or not self._consolidation_thread.is_alive()):
            self._consolidation_thread = threading.Thread(
                target=self._consolidation_loop,
                daemon=True,
                name="BrainConsolidation",
            )
            self._consolidation_thread.start()

    # ── Search & Pruning ─────────────────────────────────────────────────────

    def search_memory(self, query: str, top_k: int = 10) -> List[dict]:
        """Search all memories by keyword."""
        return self.recall_by_value(query, top_k)

    def _prune_weakest_category(self):
        """Remove the category with weakest overall strength."""
        weakest = None
        weakest_strength = float('inf')

        for cat_name, cat_data in self._data["neocortex"].items():
            if not cat_data:
                weakest = cat_name
                weakest_strength = -1
                break
            strengths = [e.get("strength", 0) for e in cat_data.values()]
            avg = sum(strengths) / max(len(strengths), 1)
            if avg < weakest_strength:
                weakest_strength = avg
                weakest = cat_name

        if weakest:
            count = len(self._data["neocortex"].get(weakest, {}))
            del self._data["neocortex"][weakest]
            print(f"[Brain] -- Pruned category '{weakest}' "
                  f"({count} memories)")

    def force_prune(self):
        """Force an immediate prune cycle."""
        self._consolidate()
        self._save()

    # ── Bulk Operations [#9] ─────────────────────────────────────────────────

    def encode_bulk(self, entries: List[Dict[str, str]]) -> int:
        """Encode multiple memories at once. Returns count encoded."""
        count = 0
        for e in entries:
            cat = e.get("category", "notes")
            key = e.get("key", "")
            val = e.get("value", "")
            if key and val:
                self.encode(cat, key, val)
                count += 1
        return count

    def encode_security_finding(self, finding: dict) -> str:
        """Store a security finding as a long-term memory."""
        vuln_class = finding.get("vuln_class", "unknown")
        file_path = finding.get("file_path", "unknown")
        cvss = finding.get("cvss_score", 0)
        confidence = finding.get("confidence", "unknown")
        summary = finding.get("summary", "")

        category = "security"
        key = f"{file_path}_{vuln_class}".replace("/", "_").replace("\\", "_")[:100]
        value = f"CVSS {cvss} | {confidence} | {summary[:150]}"

        context = {
            "vuln_class": vuln_class,
            "cvss_score": cvss,
            "confidence": confidence,
            "agent": finding.get("agent", "unknown"),
            "phase": finding.get("phase", 0),
        }

        return self.encode(category, key, value, context=context)

    def encode_security_findings(self, findings: list) -> int:
        """Store multiple security findings as long-term memories."""
        count = 0
        for finding in findings:
            self.encode_security_finding(finding)
            count += 1
        return count

    def get_security_memories(self) -> list:
        """Retrieve all security-related memories."""
        return self.recall_by_value("security", top_k=20)

    def export_memories(self) -> dict:
        """Export all memories as JSON-serializable dict (for backup)."""
        with self._lock:
            return json.loads(json.dumps(self._data, ensure_ascii=False))

    # ── Query & Stats ────────────────────────────────────────────────────────

    def all_memories(self, include_weak: bool = False) -> Dict[str, List[dict]]:
        """Get all memories grouped by category."""
        result = {}
        with self._lock:
            for cat_name, cat_data in self._data["neocortex"].items():
                entries = []
                for key, entry in cat_data.items():
                    if not include_weak and _should_prune(entry):
                        continue
                    entries.append(dict(entry))
                if entries:
                    result[cat_name] = entries
        return result

    def format_for_prompt(self, max_chars: int = 2000) -> str:
        """Format memories for system prompt inclusion."""
        sections = []

        with self._lock:
            for cat_name, cat_data in self._data["neocortex"].items():
                entries = []
                for key, entry in cat_data.items():
                    if _should_prune(entry):
                        continue
                    entries.append(entry)

                if not entries:
                    continue

                entries.sort(key=lambda e: e.get("strength", 0), reverse=True)

                lines = []
                cat_label = cat_name.replace("_", " ").title()
                lines.append(f"\n[{cat_label}]")

                for entry in entries[:15]:
                    val = entry.get("value", "")
                    lines.append(f"  • {entry['key'].replace('_', ' ').title()}: {val}")

                sections.append("\n".join(lines))

        if not sections:
            return ""

        header = (
            "[NEURAL MEMORY — Brain-inspired persistent recall]\n"
            "These are facts you remember about this person. "
            "Use naturally — don't recite the list.\n"
        )
        result = header + "".join(sections)

        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"

        return result

    def get_stats(self) -> dict:
        """Get memory system statistics."""
        total = 0
        expired = 0
        strengths = []

        with self._lock:
            for cat_data in self._data["neocortex"].values():
                for entry in cat_data.values():
                    total += 1
                    strengths.append(entry.get("strength", 0))
                    if _should_prune(entry):
                        expired += 1

        avg_strength = (sum(strengths) / len(strengths)
                        if strengths else 0)

        return {
            "total_memories":       total,
            "expired_pending_prune": expired,
            "avg_strength":         round(avg_strength, 2),
            "categories":           len(self._data["neocortex"]),
            "hippocampus_buffer":   len(self._data["hippocampus"]),
            "hebbian_links":        len(self._data["links"]),
            "total_created":        self._data["meta"]["total_memories_created"],
            "total_pruned":         self._data["meta"]["total_memories_pruned"],
        }

    def save(self):
        """Public save — persists current state to disk."""
        self._save()

    def stop(self):  # [#10]
        """Gracefully stop consolidation thread and save."""
        self._stop_event.set()
        if self._consolidation_thread and self._consolidation_thread.is_alive():
            self._consolidation_thread.join(timeout=5)
        self._save()
        print("[Brain] Stopped")


# ─── Singleton ───────────────────────────────────────────────────────────────

_brain: Optional[NeuralStore] = None
_brain_lock = threading.Lock()


def get_brain() -> NeuralStore:
    """Get the singleton brain instance."""
    global _brain
    if _brain is None:
        with _brain_lock:
            if _brain is None:
                _brain = NeuralStore()
    return _brain


# ─── Compatibility API ───────────────────────────────────────────────────────

def load_memory() -> dict:
    """Legacy compatibility: returns memories in old format."""
    brain = get_brain()
    result = {}
    for cat_name, entries in brain.all_memories().items():
        result[cat_name] = {}
        for entry in entries:
            result[cat_name][entry["key"]] = {
                "value":   entry["value"],
                "updated": entry["updated"],
            }
    return result


def update_memory(memory_update: dict) -> dict:
    """Legacy compatibility: accepts old format and encodes via neural store.
    Handles both Dict[str, dict] and Dict[str, List[dict]] (from all_memories())."""
    brain = get_brain()
    for category, items in memory_update.items():
        if isinstance(items, list):
            # all_memories() format: List[dict] with "key", "value" fields
            for entry in items:
                if isinstance(entry, dict) and "key" in entry and "value" in entry:
                    brain.encode(category, entry["key"], entry["value"])
        elif isinstance(items, dict):
            for key, entry in items.items():
                if isinstance(entry, dict) and "value" in entry:
                    brain.encode(category, key, entry["value"])
                elif isinstance(entry, str):
                    brain.encode(category, key, entry)
    return load_memory()


def format_memory_for_prompt(memory: Optional[dict] = None) -> str:
    """Legacy compatibility: uses brain's format."""
    brain = get_brain()
    return brain.format_for_prompt()
