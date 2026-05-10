#!/usr/bin/env python3
"""
dreaming.py — FRIDAY Dreaming & Replay System (v2.0)
=====================================================

New in v2.0:
  [FIX-1] Deep merge for schema evolution
  [FIX-2] force_dream_cycle skips idle check
  [FEAT-1] Cross-module integration — dreams feed curiosity queue
  [FEAT-2] Pattern decay — unconfirmed patterns fade over time
  [FEAT-3] Dream diversity — rotates through categories instead of repeating
  [FEAT-4] Dream-reality tracking — validates patterns against tool outcomes
  [FEAT-5] Curiosity-informed dreaming — prioritizes replay of curiosity targets
"""

import json
import math
import threading
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
DREAM_FILE = BRAIN_DIR / "dream_journal.json"

# ── Configuration ───────────────────────────────────────────────────────────

REPLAY_INTERVAL_SECONDS = 600       # Run dream cycle every 10 min
IDLE_THRESHOLD_SECONDS = 120        # Consider idle after 2 min of no activity
MIN_MEMORIES_FOR_DREAM = 5          # Need at least this many memories to dream
MAX_DREAM_CYCLES_PER_SESSION = 10   # Don't dream too much in one session
PATTERN_DECAY_DAYS = 7.0            # Unconfirmed patterns lose strength over this period
PATTERN_MIN_STRENGTH = 0.1          # Below this, pattern is removed


class DreamingSystem:
    """
    Dreaming and replay system for FRIDAY.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._dream_thread = None
        self._last_activity_time = time.time()
        self._dream_cycles_run = 0
        self._last_replayed_category = ""
        self._journal = self._load_journal()
        self._start_dream_loop()

    def _empty_journal(self) -> dict:
        return {
            "meta": {
                "version": 2,
                "created": datetime.now().isoformat(),
                "total_dream_cycles": 0,
                "total_patterns_found": 0,
                "total_validated": 0,
                "last_dream": "",
            },
            "dreams": [],
            "patterns": [],
            # FEAT-4: Track pattern predictions vs reality
            "validations": [
                # {
                #   "timestamp": "",
                #   "pattern": "",
                #   "predicted": "",
                #   "actual_outcome": "",
                #   "correct": False,
                # }
            ],
        }

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """FIX-1: Recursive merge for schema evolution."""
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _load_journal(self) -> dict:
        if not DREAM_FILE.exists():
            return self._empty_journal()
        try:
            raw = DREAM_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            empty = self._empty_journal()
            self._journal = self._deep_merge(empty, data)
            return self._journal
        except (json.JSONDecodeError, IOError):
            return self._empty_journal()

    def _save_journal(self):
        with self._lock:
            self._journal["meta"]["last_dream"] = datetime.now().isoformat()
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            DREAM_FILE.write_text(
                json.dumps(self._journal, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Activity tracking ──────────────────────────────────────────────

    def note_activity(self):
        """Called when any interaction happens to reset idle timer."""
        self._last_activity_time = time.time()

    def is_idle(self) -> bool:
        """Check if FRIDAY has been idle long enough to dream."""
        return (time.time() - self._last_activity_time) >= IDLE_THRESHOLD_SECONDS

    # ── FEAT-2: Pattern Decay ──────────────────────────────────────────

    def _decay_patterns(self):
        """
        Patterns that haven't been confirmed recently lose strength.
        Old weak patterns are removed entirely.
        """
        with self._lock:
            now = datetime.now()
            surviving = []
            for pattern in self._journal["patterns"]:
                last_seen = pattern.get("last_seen", "")
                try:
                    last_dt = datetime.fromisoformat(last_seen)
                    days_since = (now - last_dt).total_seconds() / 86400.0
                except (ValueError, TypeError):
                    days_since = PATTERN_DECAY_DAYS

                # Decay strength based on time since last confirmation
                if days_since > 0:
                    decay_rate = 0.05 * (days_since / PATTERN_DECAY_DAYS)
                    pattern["strength"] = max(
                        0.0,
                        pattern.get("strength", 0.5) - decay_rate
                    )

                # Keep if still strong enough
                if pattern["strength"] >= PATTERN_MIN_STRENGTH:
                    surviving.append(pattern)

            self._journal["patterns"] = surviving

    # ── FEAT-3: Dream Diversity ────────────────────────────────────────

    def _diversify_memories(self, memories: list[dict]) -> list[dict]:
        """
        Ensure replay covers diverse categories, not just the same ones.
        Rotates focus away from the last replayed category.
        """
        if not memories:
            return memories

        # Group by category
        by_category = defaultdict(list)
        for mem in memories:
            cat = mem.get("category", "unknown")
            by_category[cat].append(mem)

        # If we have a last-replayed category, deprioritize it
        categories = list(by_category.keys())
        if self._last_replayed_category in categories and len(categories) > 1:
            # Move last category to end (lower priority)
            categories.remove(self._last_replayed_category)
            categories.append(self._last_replayed_category)

        # Round-robin selection from categories
        selected = []
        max_per_cat = max(2, 20 // max(len(categories), 1))
        for cat in categories:
            pool = by_category[cat]
            random.shuffle(pool)
            selected.extend(pool[:max_per_cat])

        random.shuffle(selected)
        result = selected[:20]

        # Track what we replayed
        if result:
            cats_used = set(m.get("category", "unknown") for m in result)
            # Pick the most represented category to deprioritize next time
            cat_counts = defaultdict(int)
            for m in result:
                cat_counts[m.get("category", "unknown")] += 1
            self._last_replayed_category = max(cat_counts, key=cat_counts.get)

        return result

    # ── FEAT-5: Curiosity-Informed Dreaming ────────────────────────────

    def _get_curiosity_targets(self) -> list[str]:
        """
        Get tools/topics the curiosity module wants explored.
        Dreams will prioritize replaying memories related to these.
        """
        try:
            from brain.curiosity import get_curiosity_module
            cm = get_curiosity_module()
            queue = cm.get_curiosity_queue()
            return [item["target"] for item in queue[:3]]
        except Exception:
            return []

    def _boost_curiosity_memories(self, memories: list[dict],
                                    targets: list[str]) -> list[dict]:
        """
        Move memories related to curiosity targets to the front of replay.
        """
        if not targets:
            return memories

        target_set = set(targets)
        related = []
        unrelated = []

        for mem in memories:
            key = mem.get("key", "").lower()
            value = mem.get("value", "").lower()
            category = mem.get("category", "").lower()

            is_related = False
            for target in target_set:
                t = target.lower()
                if t in key or t in value or t in category:
                    is_related = True
                    break

            if is_related:
                related.append(mem)
            else:
                unrelated.append(mem)

        # Related memories go first
        random.shuffle(related)
        random.shuffle(unrelated)
        return related + unrelated

    # ── Replay ─────────────────────────────────────────────────────────

    def _get_memories_for_replay(self):
        """
        Get memories from the neural store for replay.
        Prioritizes: recent + medium-strength (not too strong, not pruned).
        Applies diversity and curiosity boosting.
        """
        try:
            from brain.neural_memory import get_brain
            brain = get_brain()
            all_mems = brain.all_memories()

            candidates = []
            for cat_name, entries in all_mems.items():
                for entry in entries:
                    strength = entry.get("strength", 5.0)
                    if 1.0 <= strength <= 8.0:
                        candidates.append(entry)

            if len(candidates) < MIN_MEMORIES_FOR_DREAM:
                return []

            # FEAT-3: Diversify across categories
            candidates = self._diversify_memories(candidates)

            # FEAT-5: Boost curiosity-relevant memories
            targets = self._get_curiosity_targets()
            if targets:
                candidates = self._boost_curiosity_memories(candidates, targets)

            return candidates[:20]
        except Exception as e:
            print(f"[Dreaming] Could not get memories: {e}")
            return []

    def _replay(self) -> list[dict]:
        """
        Replay phase: retrieve memories and look for patterns.
        """
        memories = self._get_memories_for_replay()
        if len(memories) < MIN_MEMORIES_FOR_DREAM:
            return []

        patterns = []

        # Pattern 1: Co-occurring categories
        cat_counts = defaultdict(int)
        for mem in memories:
            cat_counts[mem.get("category", "unknown")] += 1

        if len(cat_counts) >= 2:
            cat_pairs = defaultdict(int)
            for i, m1 in enumerate(memories):
                for m2 in memories[i + 1:]:
                    c1 = m1.get("category")
                    c2 = m2.get("category")
                    if c1 and c2 and c1 != c2:
                        pair = tuple(sorted([c1, c2]))
                        cat_pairs[pair] += 1

            for pair, count in cat_pairs.items():
                if count >= 2:
                    pattern = {
                        "type": "category_cooccurrence",
                        "pattern": f"Memories about '{pair[0]}' often appear with memories about '{pair[1]}'",
                        "confidence": min(1.0, count / 5.0),
                        "source_categories": list(pair),
                        "evidence_count": count,
                    }
                    patterns.append(pattern)

        # Pattern 2: Temporal clustering
        timestamps = []
        for mem in memories:
            ts = mem.get("created", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    timestamps.append((dt, mem))
                except (ValueError, TypeError):
                    pass

        if len(timestamps) >= 3:
            timestamps.sort(key=lambda x: x[0])
            for i in range(len(timestamps) - 2):
                gap1 = (timestamps[i + 1][0] - timestamps[i][0]).total_seconds()
                gap2 = (timestamps[i + 2][0] - timestamps[i + 1][0]).total_seconds()
                if gap1 < 300 and gap2 < 300:
                    mems_in_burst = [timestamps[i][1], timestamps[i + 1][1], timestamps[i + 2][1]]
                    cats = set(m.get("category", "?") for m in mems_in_burst)
                    if len(cats) >= 2:
                        pattern = {
                            "type": "temporal_burst",
                            "pattern": f"Rapid memory formation across categories: {', '.join(cats)}",
                            "confidence": 0.6,
                            "source_categories": list(cats),
                            "evidence_count": len(mems_in_burst),
                        }
                        patterns.append(pattern)
                        break

        # Pattern 3: Key-value repetition (same key, different values over time)
        key_values = defaultdict(list)
        for mem in memories:
            key = mem.get("key", "")
            value = mem.get("value", "")
            if key and value:
                key_values[key].append(value)

        for key, values in key_values.items():
            if len(values) >= 2 and len(set(values)) >= 2:
                pattern = {
                    "type": "value_evolution",
                    "pattern": f"'{key}' has changed over time: {' -> '.join(str(v)[:30] for v in values[:3])}",
                    "confidence": 0.7,
                    "source_categories": [],
                    "evidence_count": len(values),
                }
                patterns.append(pattern)

        # Pattern 4: Category imbalance (one category dominates)
        if cat_counts:
            total = sum(cat_counts.values())
            for cat, count in cat_counts.items():
                ratio = count / total
                if ratio > 0.6 and total >= 5:
                    pattern = {
                        "type": "category_dominance",
                        "pattern": f"Category '{cat}' dominates memory ({ratio:.0%} of recent memories)",
                        "confidence": 0.5,
                        "source_categories": [cat],
                        "evidence_count": count,
                    }
                    patterns.append(pattern)

        return patterns

    # ── FEAT-4: Dream-Reality Validation ───────────────────────────────

    def validate_pattern(self, pattern_text: str, actual_outcome: str,
                          was_correct: bool):
        """
        Record whether a dream-predicted pattern held true in reality.
        Called by main.py when tool outcomes relate to known patterns.
        """
        with self._lock:
            self._journal["validations"].append({
                "timestamp": datetime.now().isoformat(),
                "pattern": pattern_text[:200],
                "actual_outcome": actual_outcome[:200],
                "correct": was_correct,
            })
            self._journal["validations"] = self._journal["validations"][-50:]
            self._journal["meta"]["total_validated"] += 1

            # Strengthen or weaken the pattern
            for p in self._journal["patterns"]:
                if p["pattern"] == pattern_text:
                    if was_correct:
                        p["strength"] = min(1.0, p.get("strength", 0.5) + 0.15)
                        p["confirmations"] = p.get("confirmations", 0) + 1
                    else:
                        p["strength"] = max(0.0, p.get("strength", 0.5) - 0.1)
                    p["last_seen"] = datetime.now().isoformat()
                    break

            self._save_journal()

    # ── Dream cycle ─────────────────────────────────────────────────────

    def _run_dream_cycle(self, force: bool = False):
        """
        Run a full dream cycle: decay -> replay -> pattern extraction -> log.
        """
        if not force:
            if self._dream_cycles_run >= MAX_DREAM_CYCLES_PER_SESSION:
                return
            if not self.is_idle():
                return

        # FEAT-2: Decay old patterns first
        self._decay_patterns()

        patterns = self._replay()
        if not patterns:
            return

        self._dream_cycles_run += 1

        with self._lock:
            self._journal["meta"]["total_dream_cycles"] += 1

            for pattern in patterns:
                dream_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "type": pattern["type"],
                    "insight": pattern["pattern"],
                    "confidence": pattern.get("confidence", 0.5),
                    "consolidated": False,
                }
                self._journal["dreams"].append(dream_entry)
                self._journal["meta"]["total_patterns_found"] += 1

                # Update or add to persistent patterns
                found = False
                for existing in self._journal["patterns"]:
                    if existing["pattern"] == pattern["pattern"]:
                        existing["strength"] = min(
                            1.0, existing.get("strength", 0.5) + 0.1
                        )
                        existing["last_seen"] = datetime.now().isoformat()
                        existing["confirmations"] = existing.get("confirmations", 0) + 1
                        found = True
                        break

                if not found:
                    self._journal["patterns"].append({
                        "pattern": pattern["pattern"],
                        "strength": pattern.get("confidence", 0.5),
                        "first_seen": datetime.now().isoformat(),
                        "last_seen": datetime.now().isoformat(),
                        "confirmations": 1,
                        "type": pattern["type"],
                    })

            self._journal["patterns"].sort(
                key=lambda p: p.get("confirmations", 0), reverse=True)
            self._journal["patterns"] = self._journal["patterns"][:50]
            self._journal["dreams"] = self._journal["dreams"][-100:]

        self._save_journal()
        self._consolidate_to_learning(patterns)

        # FEAT-1: Feed patterns into curiosity module
        self._feed_curiosity(patterns)

        print(f"[Dreaming] Dream cycle complete: {len(patterns)} patterns found")

    def _consolidate_to_learning(self, patterns: list[dict]):
        """Feed discovered patterns into the learning engine."""
        try:
            from brain.learning import get_learning_engine
            engine = get_learning_engine()

            for p in patterns:
                if p.get("confidence", 0) >= 0.5:
                    engine.write_evolution_learning(
                        insight=f"[Dream consolidation] {p['pattern']}",
                        domain="dreaming_replay",
                    )
        except Exception as e:
            print(f"[Dreaming] Consolidation to learning failed: {e}")

    # ── FEAT-1: Cross-Module Curiosity Integration ─────────────────────

    def _feed_curiosity(self, patterns: list[dict]):
        """
        Feed dream-discovered patterns into the curiosity module.
        If a pattern mentions a tool, boost its curiosity score.
        """
        try:
            from brain.curiosity import get_curiosity_module
            cm = get_curiosity_module()

            known_tools = [
                "web_search", "weather_report", "youtube_video",
                "screen_process", "computer_settings", "browser_control",
                "file_controller", "code_helper", "desktop_control",
                "open_app", "game_updater", "flight_finder",
                "send_message", "reminder", "web_research",
                "ai_pipeline", "data_analysis", "deep_dive",
                "security_tools", "holo_builder", "holographic_map",
            ]

            for pattern in patterns:
                text = pattern.get("pattern", "").lower()
                for tool in known_tools:
                    tool_clean = tool.replace("_", " ")
                    if tool_clean in text or tool in text:
                        cm.encounter(f"dream:{tool}")
        except Exception:
            pass

    def _dream_loop(self):
        """Background thread: runs dream cycles periodically."""
        while not self._stop_event.is_set():
            self._stop_event.wait(REPLAY_INTERVAL_SECONDS)
            if self._stop_event.is_set():
                break
            try:
                self._run_dream_cycle()
            except Exception as e:
                print(f"[Dreaming] Dream cycle error: {e}")

    def _start_dream_loop(self):
        if self._dream_thread is None or not self._dream_thread.is_alive():
            self._dream_thread = threading.Thread(
                target=self._dream_loop, daemon=True
            )
            self._dream_thread.start()
            print("[Dreaming] Background dream loop started")

    # ── Public API ─────────────────────────────────────────────────────

    def force_dream_cycle(self) -> str:
        """FIX-2: Force an immediate dream cycle regardless of idle state."""
        self._dream_cycles_run = 0
        before = self._journal["meta"]["total_patterns_found"]
        self._run_dream_cycle(force=True)
        after = self._journal["meta"]["total_patterns_found"]
        new_patterns = after - before
        if new_patterns > 0:
            return f"Dream cycle complete: {new_patterns} new patterns found"
        return "Dream cycle ran: no new patterns found"

    def get_dream_journal(self) -> dict:
        """Get the full dream journal for review."""
        with self._lock:
            return dict(self._journal)

    def get_recent_dreams(self, count: int = 5) -> list[dict]:
        """Get the most recent dream entries."""
        with self._lock:
            return list(self._journal["dreams"][-count:])

    def get_strong_patterns(self, threshold: float = 0.7) -> list[dict]:
        """Get patterns that have been confirmed multiple times."""
        with self._lock:
            return [
                p for p in self._journal["patterns"]
                if p.get("confirmations", 0) >= 2 or p.get("strength", 0) >= threshold
            ]

    def format_for_prompt(self, max_chars: int = 400) -> str:
        """Format dream insights for system prompt inclusion."""
        patterns = self.get_strong_patterns(threshold=0.6)
        validations = []
        with self._lock:
            recent_vals = self._journal.get("validations", [])[-3:]

        if not patterns and not recent_vals:
            return ""

        parts = ["[DREAM INSIGHTS — Patterns I've noticed]"]
        for p in patterns[:3]:
            conf = p.get("confirmations", 1)
            parts.append(f"  \u2022 {p['pattern'][:80]} (seen {conf}x)")

        if recent_vals:
            correct = sum(1 for v in recent_vals if v.get("correct", False))
            parts.append(f"  Pattern accuracy: {correct}/{len(recent_vals)} recent validations")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n  [...]"
        return result

    def get_stats(self) -> dict:
        """Get dreaming system statistics."""
        with self._lock:
            total_val = len(self._journal.get("validations", []))
            correct_val = sum(
                1 for v in self._journal.get("validations", [])
                if v.get("correct", False)
            )
            return {
                "total_dream_cycles": self._journal["meta"]["total_dream_cycles"],
                "total_patterns": self._journal["meta"]["total_patterns_found"],
                "active_patterns": len(self._journal["patterns"]),
                "session_dreams": self._dream_cycles_run,
                "is_idle": self.is_idle(),
                "idle_seconds": int(time.time() - self._last_activity_time),
                "validations_total": total_val,
                "validations_correct": correct_val,
                "pattern_accuracy": (
                    f"{correct_val}/{total_val}" if total_val > 0 else "none"
                ),
            }


# ── Singleton ───────────────────────────────────────────────────────────────

_dreaming = None
_dreaming_lock = threading.Lock()


def get_dreaming_system() -> DreamingSystem:
    """Get the singleton dreaming system instance."""
    global _dreaming
    if _dreaming is None:
        with _dreaming_lock:
            if _dreaming is None:
                _dreaming = DreamingSystem()
    return _dreaming
