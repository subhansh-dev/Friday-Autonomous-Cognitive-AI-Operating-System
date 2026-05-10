"""
global_workspace.py — FRIDAY Global Workspace (Thalamus)
========================================================

The central integration hub inspired by Bernard Baars' Global Workspace Theory.
Connects all 20+ brain modules into one unified consciousness.

Dual-path architecture:
  - Hot Path: asyncio event bus, attention scoring, real-time broadcast (<5ms)
  - Cold Path: event persistence, pattern detection, consolidation (background)

This is the thalamus of FRIDAY — the hub where information competes for
attention and winning events get broadcast to all modules simultaneously.
"""

import asyncio
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from abc import ABC, abstractmethod

from brain.workspace_events import EventType, WorkspaceEvent


BRAIN_DIR = Path(__file__).parent.resolve()
EVENT_STORE_FILE = BRAIN_DIR / "workspace_events.jsonl"
PATTERNS_FILE = BRAIN_DIR / "workspace_patterns.json"
ATTENTION_WEIGHTS_FILE = BRAIN_DIR / "attention_weights.json"

# Attention thresholds
CONSCIOUS_THRESHOLD = 0.7       # Broadcast to ALL modules
SELECTIVE_THRESHOLD = 0.4       # Broadcast to relevant modules only
BACKGROUND_THRESHOLD = 0.2      # Logged but not broadcast

# Buffer sizes
WORKSPACE_BUFFER_SIZE = 20      # Recent events in active consciousness
EVENT_STORE_MAX_EVENTS = 10000  # Max events in persistent store

# Cold path triggers (idle seconds)
LIGHT_SLEEP_IDLE = 120          # 2 min
DEEP_SLEEP_IDLE = 600           # 10 min
REM_SLEEP_IDLE = 900            # 15 min
GROWTH_PHASE_IDLE = 1800        # 30 min

# Habituation
HABITUATION_DECAY = 0.85        # Repeated events lose 15% importance each

# Burst detection
BURST_THRESHOLD = 5             # Events in burst window
BURST_WINDOW_MS = 100           # Milliseconds
BURST_MAX_BROADCAST = 3         # Only top N in crisis mode


# ─── Workspace Participant (Abstract Base) ────────────────────────────────

class WorkspaceParticipant(ABC):
    """Base class for all modules connected to the Global Workspace."""

    @abstractmethod
    async def on_workspace_event(self, event: WorkspaceEvent):
        """Called when the workspace broadcasts an event."""
        pass

    def get_interests(self) -> List[EventType]:
        """What event types this module wants to hear about. Override to filter."""
        return list(EventType)  # Default: interested in everything

    def get_name(self) -> str:
        """Module name for logging."""
        return self.__class__.__name__


# ─── Attention Engine ─────────────────────────────────────────────────────

class AttentionEngine:
    """
    Scores events on multiple dimensions and decides what gets conscious attention.
    Adaptive: learns which attention factors predict useful outcomes over time.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._weights = self._load_weights()
        self._habituation_cache: Dict[str, float] = {}  # event_signature -> count
        self._burst_times: deque = deque()

    def _load_weights(self) -> dict:
        try:
            if ATTENTION_WEIGHTS_FILE.exists():
                with open(ATTENTION_WEIGHTS_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            "urgency": 0.30,
            "goal_relevance": 0.25,
            "emotional_salience": 0.20,
            "surprise": 0.15,
            "novelty": 0.10,
        }

    def _save_weights(self):
        try:
            with open(ATTENTION_WEIGHTS_FILE, "w") as f:
                json.dump(self._weights, f, indent=2)
        except Exception:
            pass

    def score_event(self, event: WorkspaceEvent,
                    urgency: float = 0.0,
                    goal_relevance: float = 0.0,
                    emotional_salience: float = 0.0,
                    surprise: float = 0.0,
                    novelty: float = 0.0) -> float:
        """Compute importance score for an event."""
        with self._lock:
            w = self._weights
            raw_score = (
                w["urgency"] * urgency +
                w["goal_relevance"] * goal_relevance +
                w["emotional_salience"] * emotional_salience +
                w["surprise"] * surprise +
                w["novelty"] * novelty
            )

            # Apply habituation — repeated identical events lose importance
            sig = f"{event.source}_{event.type.value}"
            habit_count = self._habituation_cache.get(sig, 0)
            habituation_factor = HABITUATION_DECAY ** habit_count
            self._habituation_cache[sig] = habit_count + 1

            # Decay habituation cache periodically (every 100 events)
            if sum(self._habituation_cache.values()) > 100:
                self._habituation_cache = {
                    k: max(0, v - 1)
                    for k, v in self._habituation_cache.items()
                    if v > 1
                }

            return max(0.0, min(1.0, raw_score * habituation_factor))

    def classify_importance(self, score: float) -> str:
        """Classify an importance score into a broadcast level."""
        if score >= CONSCIOUS_THRESHOLD:
            return "conscious"
        elif score >= SELECTIVE_THRESHOLD:
            return "selective"
        elif score >= BACKGROUND_THRESHOLD:
            return "background"
        return "filtered"

    def is_burst(self) -> bool:
        """Detect if we're in a burst of rapid events."""
        now = time.time() * 1000
        self._burst_times.append(now)
        # Clean old entries
        while self._burst_times and self._burst_times[0] < now - BURST_WINDOW_MS:
            self._burst_times.popleft()
        return len(self._burst_times) >= BURST_THRESHOLD

    def adjust_weights(self, factor_scores: dict, outcome_useful: bool, lr: float = 0.01):
        """
        Adapt attention weights based on whether the attended event led to useful outcomes.
        Called by cold path optimization.
        """
        with self._lock:
            direction = 1.0 if outcome_useful else -1.0
            for factor, score in factor_scores.items():
                if factor in self._weights and score > 0:
                    self._weights[factor] += lr * direction * score
            # Normalize
            total = sum(self._weights.values())
            if total > 0:
                self._weights = {k: v / total for k, v in self._weights.items()}
            self._save_weights()


# ─── Workspace Buffer ─────────────────────────────────────────────────────

class WorkspaceBuffer:
    """Fixed-size buffer of recent workspace events (active consciousness)."""

    def __init__(self, max_size: int = WORKSPACE_BUFFER_SIZE):
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = threading.RLock()

    def push(self, event: WorkspaceEvent):
        with self._lock:
            self._buffer.append(event)

    def get_recent(self, n: int = 10) -> List[WorkspaceEvent]:
        with self._lock:
            return list(self._buffer)[-n:]

    def get_all(self) -> List[WorkspaceEvent]:
        with self._lock:
            return list(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()


# ─── Event Store (Cold Path) ──────────────────────────────────────────────

class EventStore:
    """Persistent log of all workspace events for pattern detection."""

    def __init__(self, max_events: int = EVENT_STORE_MAX_EVENTS):
        self._events: List[dict] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        try:
            if EVENT_STORE_FILE.exists():
                with open(EVENT_STORE_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._events.append(json.loads(line))
                # Trim to max
                if len(self._events) > max_events:
                    self._events = self._events[-max_events:]
        except Exception:
            self._events = []

    def append(self, event: WorkspaceEvent):
        with self._lock:
            self._events.append(event.to_dict())
            # Trim
            if len(self._events) > EVENT_STORE_MAX_EVENTS:
                self._events = self._events[-EVENT_STORE_MAX_EVENTS:]

    def flush(self):
        """Write events to disk. Called periodically."""
        with self._lock:
            try:
                with open(EVENT_STORE_FILE, "w") as f:
                    for evt in self._events:
                        f.write(json.dumps(evt) + "\n")
            except Exception:
                pass

    def get_recent(self, n: int = 100) -> List[dict]:
        with self._lock:
            return self._events[-n:]

    def get_by_type(self, event_type: str, n: int = 50) -> List[dict]:
        with self._lock:
            return [e for e in self._events if e.get("type") == event_type][-n:]

    def get_since(self, timestamp: float) -> List[dict]:
        with self._lock:
            return [e for e in self._events if e.get("timestamp", 0) >= timestamp]


# ─── Pattern Detector (Cold Path) ─────────────────────────────────────────

class PatternDetector:
    """Analyzes event store for cross-module patterns."""

    def __init__(self, event_store: EventStore):
        self._store = event_store
        self._patterns: List[dict] = []
        self._lock = threading.RLock()
        self._load_patterns()

    def _load_patterns(self):
        try:
            if PATTERNS_FILE.exists():
                with open(PATTERNS_FILE, "r") as f:
                    self._patterns = json.load(f)
        except Exception:
            self._patterns = []

    def _save_patterns(self):
        try:
            with open(PATTERNS_FILE, "w") as f:
                json.dump(self._patterns, f, indent=2)
        except Exception:
            pass

    def detect_patterns(self) -> List[dict]:
        """Analyze recent events for patterns. Called during deep sleep."""
        events = self._store.get_recent(500)
        if len(events) < 20:
            return []

        new_patterns = []

        # Pattern 1: Tool failure correlations
        tool_failures = [e for e in events if e.get("type") == "tool_result"
                         and not e.get("content", {}).get("success", True)]
        if len(tool_failures) >= 3:
            failure_tools = defaultdict(int)
            for f in tool_failures:
                tool = f.get("content", {}).get("tool", "unknown")
                failure_tools[tool] += 1
            for tool, count in failure_tools.items():
                if count >= 2:
                    new_patterns.append({
                        "type": "tool_failure_cluster",
                        "tool": tool,
                        "count": count,
                        "detected_at": time.time(),
                        "strength": min(1.0, count / 5.0),
                    })

        # Pattern 2: User input -> tool sequences
        user_inputs = [e for e in events if e.get("type") == "user_input"]
        tool_calls = [e for e in events if e.get("type") == "tool_call"]
        if user_inputs and tool_calls:
            # Find tool calls that follow user inputs within 30s
            for ui in user_inputs[-10:]:
                ui_time = ui.get("timestamp", 0)
                following_tools = [
                    tc for tc in tool_calls
                    if 0 < tc.get("timestamp", 0) - ui_time < 30
                ]
                if len(following_tools) >= 2:
                    tool_seq = [t.get("content", {}).get("tool", "?") for t in following_tools]
                    new_patterns.append({
                        "type": "user_tool_sequence",
                        "sequence": tool_seq,
                        "detected_at": time.time(),
                        "strength": 0.6,
                    })

        # Pattern 3: Emotional state after events
        emotion_changes = [e for e in events if e.get("type") == "emotion_change"]
        errors = [e for e in events if e.get("type") == "error"]
        if emotion_changes and errors:
            frustration_events = [
                e for e in emotion_changes
                if e.get("content", {}).get("emotion") == "frustration"
            ]
            if len(frustration_events) >= 2:
                new_patterns.append({
                    "type": "frustration_after_errors",
                    "count": len(frustration_events),
                    "detected_at": time.time(),
                    "strength": min(1.0, len(frustration_events) / 5.0),
                })

        # Merge with existing patterns
        with self._lock:
            self._patterns.extend(new_patterns)
            # Decay old patterns
            now = time.time()
            self._patterns = [
                p for p in self._patterns
                if now - p.get("detected_at", 0) < 7 * 86400  # 7 days
                and p.get("strength", 0) > 0.1
            ]
            self._save_patterns()

        return new_patterns

    def get_patterns(self) -> List[dict]:
        with self._lock:
            return list(self._patterns)


# ─── Global Workspace ─────────────────────────────────────────────────────

class GlobalWorkspace:
    """
    The central integration hub — FRIDAY's thalamus.

    Hot Path: event bus + attention + broadcast (<5ms)
    Cold Path: event store + pattern detection + consolidation (background)
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Hot path components
        self._attention = AttentionEngine()
        self._buffer = WorkspaceBuffer()
        self._subscribers: Dict[EventType, List[WorkspaceParticipant]] = defaultdict(list)
        self._all_participants: List[WorkspaceParticipant] = []

        # Cold path components
        self._event_store = EventStore()
        self._pattern_detector = PatternDetector(self._event_store)

        # State tracking
        self._active_goals: List[str] = []
        self._current_tool: Optional[str] = None
        self._last_activity_time = time.time()
        self._event_count = 0
        self._running = True

        # Cold path thread
        self._cold_thread = threading.Thread(target=self._cold_path_loop, daemon=True)
        self._cold_thread.start()

        # Event store flush thread
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

        print("[GLOBAL_WORKSPACE] Initialized — thalamus online", flush=True)

    # ─── Module Registration ──────────────────────────────────────────────

    def register(self, participant: WorkspaceParticipant):
        """Register a module as a workspace participant."""
        with self._lock:
            self._all_participants.append(participant)
            interests = participant.get_interests()
            for event_type in interests:
                self._subscribers[event_type].append(participant)
            print(f"[GLOBAL_WORKSPACE] Registered: {participant.get_name()} "
                  f"(interests: {len(interests)} event types)", flush=True)

    def unregister(self, participant: WorkspaceParticipant):
        """Remove a module from the workspace."""
        with self._lock:
            if participant in self._all_participants:
                self._all_participants.remove(participant)
            for event_type in EventType:
                if participant in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(participant)

    # ─── Hot Path: Publish + Broadcast ────────────────────────────────────

    async def publish(self, event: WorkspaceEvent,
                      urgency: float = 0.0,
                      goal_relevance: float = 0.0,
                      emotional_salience: float = 0.0,
                      surprise: float = 0.0,
                      novelty: float = 0.0) -> WorkspaceEvent:
        """
        Publish an event to the workspace. Scores importance, broadcasts if above threshold.
        Returns the event with its computed importance.
        """
        # Score the event
        event.importance = self._attention.score_event(
            event,
            urgency=urgency,
            goal_relevance=goal_relevance,
            emotional_salience=emotional_salience,
            surprise=surprise,
            novelty=novelty,
        )

        # Check for burst
        in_burst = self._attention.is_burst()

        # Classify and broadcast
        level = self._attention.classify_importance(event.importance)

        # Store in buffer
        self._buffer.push(event)

        # Store in event store (cold path)
        self._event_store.append(event)

        # Update activity tracking
        self._last_activity_time = time.time()
        self._event_count += 1

        if level == "filtered":
            return event

        if event.vetoed:
            return event

        # Determine subscribers
        if level == "conscious":
            targets = list(self._all_participants)
        else:
            targets = list(self._subscribers.get(event.type, []))

        # Burst mode: limit broadcast
        if in_burst and len(targets) > BURST_MAX_BROADCAST:
            targets = targets[:BURST_MAX_BROADCAST]

        # Broadcast in parallel
        await self._broadcast(event, targets)

        return event

    async def _broadcast(self, event: WorkspaceEvent, targets: List[WorkspaceParticipant]):
        """Broadcast an event to target modules in parallel."""
        tasks = []
        for participant in targets:
            tasks.append(self._safe_deliver(participant, event))
        if tasks:
            await asyncio.gather(*tasks)

    async def _safe_deliver(self, participant: WorkspaceParticipant, event: WorkspaceEvent):
        """Deliver an event to a module, catching errors."""
        try:
            await participant.on_workspace_event(event)
        except Exception as e:
            print(f"[GLOBAL_WORKSPACE] Error delivering to {participant.get_name()}: {e}", flush=True)

    # ─── Workspace State ──────────────────────────────────────────────────

    def get_recent_events(self, n: int = 10) -> List[WorkspaceEvent]:
        """Get recent workspace events."""
        return self._buffer.get_recent(n)

    def set_active_goals(self, goals: List[str]):
        """Update the current active goals."""
        self._active_goals = goals

    def get_active_goals(self) -> List[str]:
        return list(self._active_goals)

    def set_current_tool(self, tool: Optional[str]):
        self._current_tool = tool

    def get_idle_seconds(self) -> float:
        """How long since the last workspace event."""
        return time.time() - self._last_activity_time

    def get_stats(self) -> dict:
        """Workspace statistics."""
        return {
            "total_events": self._event_count,
            "buffer_size": len(self._buffer.get_all()),
            "participants": len(self._all_participants),
            "idle_seconds": round(self.get_idle_seconds(), 1),
            "active_goals": self._active_goals,
            "attention_weights": self._attention._weights,
            "patterns_detected": len(self._pattern_detector.get_patterns()),
        }

    # ─── Cold Path ────────────────────────────────────────────────────────

    def _cold_path_loop(self):
        """Background thread for cold path processing."""
        last_deep = 0
        last_rem = 0
        last_growth = 0

        while self._running:
            try:
                idle = self.get_idle_seconds()
                now = time.time()

                if idle >= LIGHT_SLEEP_IDLE:
                    # Light sleep: memory consolidation (handled by existing modules)
                    pass

                if idle >= DEEP_SLEEP_IDLE and now - last_deep > DEEP_SLEEP_IDLE:
                    last_deep = now
                    self._run_deep_sleep()

                if idle >= REM_SLEEP_IDLE and now - last_rem > REM_SLEEP_IDLE:
                    last_rem = now
                    self._run_rem_sleep()

                if idle >= GROWTH_PHASE_IDLE and now - last_growth > GROWTH_PHASE_IDLE:
                    last_growth = now
                    self._run_growth_phase()

                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"[GLOBAL_WORKSPACE] Cold path error: {e}", flush=True)
                time.sleep(60)

    def _run_deep_sleep(self):
        """Deep sleep: pattern detection and learning consolidation."""
        print("[GLOBAL_WORKSPACE] Deep sleep: detecting patterns...", flush=True)
        patterns = self._pattern_detector.detect_patterns()
        if patterns:
            print(f"[GLOBAL_WORKSPACE] Found {len(patterns)} new patterns", flush=True)

    def _run_rem_sleep(self):
        """REM sleep: dreaming integration. Triggers existing dreaming module."""
        print("[GLOBAL_WORKSPACE] REM sleep: triggering dream cycle...", flush=True)
        # The dreaming module handles this internally via its own thread
        # We just trigger a consolidation event
        event = WorkspaceEvent(
            source="global_workspace",
            type=EventType.CONSOLIDATION_TRIGGER,
            content={"phase": "rem_sleep", "patterns": self._pattern_detector.get_patterns()},
            importance=0.3,
        )
        # Schedule broadcast on the event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.publish(event), loop)
        except RuntimeError:
            pass

    def _run_growth_phase(self):
        """Growth phase: attention weight optimization."""
        print("[GLOBAL_WORKSPACE] Growth phase: optimizing attention weights...", flush=True)
        # Analyze which events led to useful outcomes
        recent = self._event_store.get_recent(200)
        tool_results = [e for e in recent if e.get("type") == "tool_result"]

        if len(tool_results) < 10:
            return

        # Check if high-importance events led to successful outcomes
        for tr in tool_results:
            success = tr.get("content", {}).get("success", False)
            importance = tr.get("importance", 0.5)
            if importance > 0.5:
                # This was an attended event — did it lead to success?
                self._attention.adjust_weights(
                    {"urgency": importance, "goal_relevance": importance},
                    outcome_useful=success,
                )

    def _flush_loop(self):
        """Periodically flush event store to disk."""
        while self._running:
            try:
                time.sleep(10)
                self._event_store.flush()
            except Exception:
                pass

    def shutdown(self):
        """Clean shutdown."""
        self._running = False
        self._event_store.flush()


# ─── Singleton ────────────────────────────────────────────────────────────

_workspace: Optional[GlobalWorkspace] = None
_init_lock = threading.Lock()


def get_global_workspace() -> GlobalWorkspace:
    """Get or create the singleton GlobalWorkspace."""
    global _workspace
    if _workspace is None:
        with _init_lock:
            if _workspace is None:
                _workspace = GlobalWorkspace()
    return _workspace
