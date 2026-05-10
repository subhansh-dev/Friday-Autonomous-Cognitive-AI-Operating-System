#!/usr/bin/env python3
"""
memory_coordinator.py — FRIDAY Unified Memory Coordinator
===========================================================

Single API that unifies all of FRIDAY's memory systems:
- Neural Store (Hebbian, synaptic decay, consolidation)
- Vector Memory (embedding-based semantic search)
- Episodic Memory (timestamped events, conversation tracking)
- Long-Term Memory (structured facts: identity, preferences, etc.)
- Learning Engine (Q-values, error patterns, reflections)
- Self-Model (capabilities, growth, personality)

Provides:
- Unified encode/recall/search across all stores
- Automatic cross-store linking
- Smart routing (decides which store to use for each query)
- Format for prompt (combines all stores into system prompt context)
"""

import threading
import time
from datetime import datetime
from typing import Optional, List, Dict


class MemoryCoordinator:
    """
    Unified memory API for FRIDAY.

    Instead of calling each memory store individually,
    the coordinator provides a single interface that routes
    queries to the appropriate stores and merges results.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._initialized = False
        self._brain = None
        self._vector = None
        self._episodic = None
        self._learning = None
        self._self_model = None
        self._self_awareness = None
        self._procedural = None

    def _ensure_initialized(self):
        """Lazy initialization of all memory stores."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            # Neural store
            try:
                from brain.neural_memory import get_brain
                self._brain = get_brain()
            except Exception as e:
                print(f"[Coordinator] Neural store: {e}")

            # Vector memory
            try:
                from brain.vector_memory import get_vector_memory
                self._vector = get_vector_memory()
            except Exception as e:
                print(f"[Coordinator] Vector memory: {e}")

            # Episodic memory
            try:
                from brain.episodic_memory import get_episodic_memory
                self._episodic = get_episodic_memory()
            except Exception as e:
                print(f"[Coordinator] Episodic memory: {e}")

            # Learning engine
            try:
                from brain.learning import get_learning_engine
                self._learning = get_learning_engine()
            except Exception as e:
                print(f"[Coordinator] Learning engine: {e}")

            # Self model
            try:
                from brain.self_model import get_self_model
                self._self_model = get_self_model()
            except Exception as e:
                print(f"[Coordinator] Self model: {e}")

            # Self-awareness (consciousness engine)
            try:
                from brain.self_awareness import get_self_awareness
                self._self_awareness = get_self_awareness()
            except Exception as e:
                print(f"[Coordinator] Self-awareness: {e}")

            # Procedural memory (learned skill templates)
            try:
                from brain.procedural_memory import get_procedural_memory
                self._procedural = get_procedural_memory()
            except Exception as e:
                print(f"[Coordinator] Procedural memory: {e}")

            self._initialized = True
            print("[Coordinator] All memory stores initialized")

    # ── Unified Encode ──────────────────────────────────────────────────

    def remember(self, category: str, key: str, value: str,
                 context: Optional[dict] = None,
                 importance: float = 7.0) -> str:
        """
        Remember something across all relevant stores.

        Args:
            category: Memory category (identity, preference, fact, etc.)
            key: Memory key
            value: Memory value
            context: Optional context dict
            importance: 1-10 importance score

        Returns:
            memory_id
        """
        self._ensure_initialized()
        memory_id = ""

        # 1. Neural store (always)
        if self._brain:
            memory_id = self._brain.encode(category, key, value, context)
            print(f"[Coordinator] Remembered: {memory_id}")

        # 2. Episodic memory (as an event)
        if self._episodic:
            self._episodic.encode_event(
                event_type="memory_encode",
                content=f"{key}: {value}",
                context={"category": category, "memory_id": memory_id},
                importance=importance,
            )

        # 3. Vector memory (index the new entry)
        if self._vector and memory_id:
            self._vector.index_single(
                entry_id=memory_id,
                text=f"{key}: {value}",
                source="neural",
                category=category,
                strength=importance,
            )

        return memory_id

    def record_event(self, event_type: str, content: str,
                     context: Optional[dict] = None,
                     importance: float = 5.0) -> str:
        """
        Record an event in episodic memory.

        Args:
            event_type: Type of event (conversation, tool_call, error, etc.)
            content: What happened
            context: Additional context
            importance: 1-10 importance score

        Returns:
            event_id
        """
        self._ensure_initialized()
        event_id = ""

        if self._episodic:
            event_id = self._episodic.encode_event(
                event_type=event_type,
                content=content,
                context=context,
                importance=importance,
            )

        return event_id

    # ── Unified Recall ──────────────────────────────────────────────────

    def recall(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Unified recall: search across all memory stores.

        Returns a merged, ranked list of results from:
        - Vector memory (semantic similarity)
        - Neural store (keyword match + strength)
        - Episodic memory (recent events)
        - Long-term memory (structured facts)

        Each result has: source, text, score, metadata
        """
        self._ensure_initialized()
        all_results = []

        # 1. Vector memory (semantic search — highest priority)
        if self._vector:
            try:
                vector_results = self._vector.search(query, top_k=top_k)
                for r in vector_results:
                    all_results.append({
                        "source": "vector",
                        "text": r["text"],
                        "score": r["similarity"] * 0.4,
                        "id": r["id"],
                        "metadata": {
                            "vector_similarity": r["similarity"],
                            "original_source": r.get("source", ""),
                            "category": r.get("category", ""),
                        },
                    })
            except Exception:
                pass

        # 2. Neural store (keyword search + Hebbian strength)
        if self._brain:
            try:
                neural_results = self._brain.recall_by_value(query, top_k=top_k)
                for r in neural_results:
                    all_results.append({
                        "source": "neural",
                        "text": f"{r.get('key', '')}: {r.get('value', '')}",
                        "score": (r.get("strength", 5.0) / 10.0) * 0.3,
                        "id": r.get("memory_id", ""),
                        "metadata": {
                            "strength": r.get("strength", 0),
                            "category": r.get("category", ""),
                            "access_count": r.get("access_count", 0),
                        },
                    })
            except Exception:
                pass

        # 3. Episodic memory (recent events)
        if self._episodic:
            try:
                ep_results = self._episodic.search_events(query, top_k=top_k // 2)
                for r in ep_results:
                    all_results.append({
                        "source": "episodic",
                        "text": f"[{r.get('type', '?')}] {r.get('content', '')}",
                        "score": (r.get("strength", 5.0) / 10.0) * 0.2,
                        "id": r.get("event_id", ""),
                        "metadata": {
                            "event_type": r.get("type", ""),
                            "timestamp": r.get("timestamp", ""),
                            "episode_id": r.get("episode_id", ""),
                        },
                    })
            except Exception:
                pass

        # 4. Long-term memory (structured facts)
        try:
            from memory.memory_manager import load_memory
            lt_mem = load_memory()
            for cat_name, items in lt_mem.items():
                if not isinstance(items, dict):
                    continue
                for key, entry in items.items():
                    if not isinstance(entry, dict):
                        continue
                    val = entry.get("value", "")
                    text = f"{key}: {val}"
                    q = query.lower()
                    score = 0
                    if q in text.lower():
                        score = 2
                    elif any(w in text.lower() for w in q.split() if len(w) > 3):
                        score = 1
                    if score > 0:
                        all_results.append({
                            "source": "long_term",
                            "text": text,
                            "score": score * 0.1,
                            "id": f"lt:{cat_name}:{key}",
                            "metadata": {"category": cat_name},
                        })
        except Exception:
            pass

        # Deduplicate by text similarity
        seen_texts = set()
        unique_results = []
        for r in all_results:
            text_key = r["text"][:100].lower()
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                unique_results.append(r)

        # Sort by combined score
        unique_results.sort(key=lambda r: r["score"], reverse=True)
        return unique_results[:top_k]

    def recall_fact(self, category: str, key: str) -> Optional[str]:
        """Recall a specific fact from the neural store."""
        self._ensure_initialized()
        if self._brain:
            return self._brain.remember(category, key)
        return None

    # ── Indexing ────────────────────────────────────────────────────────

    def reindex_vector_store(self) -> int:
        """Re-index all memory stores into the vector store."""
        self._ensure_initialized()
        if self._vector:
            return self._vector.index_all_stores()
        return 0

    # ── Consolidation ───────────────────────────────────────────────────

    def consolidate_all(self):
        """Run consolidation across all memory stores."""
        self._ensure_initialized()

        if self._brain:
            try:
                self._brain.force_prune()
            except Exception:
                pass

        if self._episodic:
            try:
                self._episodic.consolidate()
            except Exception:
                pass

        if self._learning:
            try:
                self._learning.consolidate()
            except Exception:
                pass

        # Re-index after consolidation
        if self._vector:
            try:
                self._vector.index_all_stores()
            except Exception:
                pass

        print("[Coordinator] Consolidation complete across all stores")

    # ── Format for Prompt ───────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 3000) -> str:
        """
        Format all memory stores into a single system prompt section.
        Combines: neural memory, episodic, self-model, learnings, dreams.
        """
        self._ensure_initialized()
        sections = []

        # Neural memory (factual knowledge)
        if self._brain:
            try:
                neural = self._brain.format_for_prompt(max_chars=1200)
                if neural:
                    sections.append(neural)
            except Exception:
                pass

        # Long-term structured memory
        try:
            from memory.memory_manager import load_memory, format_memory_for_prompt
            lt = format_memory_for_prompt(load_memory())
            if lt:
                sections.append(lt)
        except Exception:
            pass

        # Episodic (recent events)
        if self._episodic:
            try:
                ep = self._episodic.format_for_prompt(max_chars=400)
                if ep:
                    sections.append(ep)
            except Exception:
                pass

        # Self-model (capabilities)
        if self._self_model:
            try:
                sm = self._self_model.format_for_prompt(max_chars=400)
                if sm:
                    sections.append(sm)
            except Exception:
                pass

        # Self-awareness (consciousness state)
        if self._self_awareness:
            try:
                sa = self._self_awareness.format_for_prompt(max_chars=600)
                if sa:
                    sections.append(sa)
            except Exception:
                pass

        # Learnings
        if self._learning:
            try:
                lr = self._learning.format_learnings_for_prompt(max_entries=3)
                if lr:
                    sections.append(lr)
            except Exception:
                pass

        # Procedural memory (learned skill templates)
        if self._procedural:
            try:
                pm = self._procedural.format_for_prompt(max_chars=400)
                if pm:
                    sections.append(pm)
            except Exception:
                pass

        # Dream insights
        try:
            from brain.dreaming import get_dreaming_system
            dreams = get_dreaming_system()
            dr = dreams.format_for_prompt(max_chars=300)
            if dr:
                sections.append(dr)
        except Exception:
            pass

        # Curiosity state
        try:
            from brain.curiosity import get_curiosity_module
            curiosity = get_curiosity_module()
            cr = curiosity.format_for_prompt(max_chars=300)
            if cr:
                sections.append(cr)
        except Exception:
            pass

        # Vector memory stats
        if self._vector:
            try:
                vm = self._vector.format_for_prompt(max_chars=200)
                if vm:
                    sections.append(vm)
            except Exception:
                pass

        result = "\n\n".join(sections)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"

        return result

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get unified memory statistics."""
        self._ensure_initialized()
        stats = {}

        if self._brain:
            try:
                stats["neural"] = self._brain.get_stats()
            except Exception:
                stats["neural"] = {"error": "unavailable"}

        if self._vector:
            try:
                stats["vector"] = self._vector.get_stats()
            except Exception:
                stats["vector"] = {"error": "unavailable"}

        if self._episodic:
            try:
                stats["episodic"] = self._episodic.get_stats()
            except Exception:
                stats["episodic"] = {"error": "unavailable"}

        if self._learning:
            try:
                stats["learning"] = self._learning.get_stats()
            except Exception:
                stats["learning"] = {"error": "unavailable"}

        if self._self_model:
            try:
                stats["self_model"] = self._self_model.get_summary()
            except Exception:
                stats["self_model"] = {"error": "unavailable"}

        if self._self_awareness:
            try:
                stats["self_awareness"] = self._self_awareness.get_consciousness_state()
            except Exception:
                stats["self_awareness"] = {"error": "unavailable"}

        if self._procedural:
            try:
                stats["procedural"] = self._procedural.get_stats()
            except Exception:
                stats["procedural"] = {"error": "unavailable"}

        return stats

    # ── Lifecycle ───────────────────────────────────────────────────────

    def save_all(self):
        """Save all memory stores to disk."""
        self._ensure_initialized()

        if self._brain:
            try:
                self._brain.save()
            except Exception:
                pass

        if self._episodic:
            try:
                self._episodic.stop()
            except Exception:
                pass

        if self._self_model:
            try:
                self._self_model.flush()
            except Exception:
                pass

        if self._self_awareness:
            try:
                self._self_awareness.flush()
            except Exception:
                pass

        if self._vector:
            try:
                self._vector._save_index()
            except Exception:
                pass

        print("[Coordinator] All stores saved")

    def stop_all(self):
        """Gracefully stop all memory stores."""
        self.save_all()

        if self._brain:
            try:
                self._brain.stop()
            except Exception:
                pass

        if self._learning:
            try:
                self._learning.stop()
            except Exception:
                pass

        if self._self_awareness:
            try:
                self._self_awareness.stop()
            except Exception:
                pass

        print("[Coordinator] All stores stopped")


# ── Singleton ───────────────────────────────────────────────────────────

_coordinator = None
_coordinator_lock = threading.Lock()


def get_memory_coordinator() -> MemoryCoordinator:
    """Get the singleton memory coordinator."""
    global _coordinator
    if _coordinator is None:
        with _coordinator_lock:
            if _coordinator is None:
                _coordinator = MemoryCoordinator()
    return _coordinator
