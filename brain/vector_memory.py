#!/usr/bin/env python3
"""
vector_memory.py — FRIDAY Semantic Vector Memory
==================================================

Embedding-based semantic search over all memory stores.
Uses sentence-transformers for dense vector representations
and numpy for fast cosine similarity search.

Architecture:
- Lazy model loading: embeddings model loads on first query, not at startup
- Auto-indexing: periodically re-indexes all memory stores
- Persistent index: vectors cached to disk to avoid re-embedding on restart
- Hybrid search: combines vector similarity with keyword matching
"""

import json
import threading
import time
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
INDEX_FILE = BRAIN_DIR / "vector_index.json"
EMBEDDINGS_FILE = BRAIN_DIR / "vector_embeddings.npz"

# Re-index every 10 minutes
REINDEX_INTERVAL_SECONDS = 600

# Embedding model (lazy-loaded)
_MODEL_NAME = "all-MiniLM-L6-v2"
_EMBEDDING_DIM = 384


class VectorMemory:
    """
    Semantic search over FRIDAY's memory stores using dense embeddings.

    Provides:
    - Semantic similarity search (find memories by meaning, not just keywords)
    - Cross-store search (searches neural, long-term, episodic, learnings)
    - Hybrid scoring (combines vector similarity with recency and strength)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._model_loading = False
        self._model_loaded = False

        # Index data
        self._entries: List[dict] = []  # [{id, text, source, metadata}]
        self._vectors: Optional[np.ndarray] = None  # (N, 384) float32

        # Load cached index
        self._load_index()

    # ── Model Loading (Lazy) ────────────────────────────────────────────

    def _ensure_model(self):
        """Lazy-load the sentence-transformers model on first use."""
        if self._model_loaded:
            return True
        if self._model_loading:
            # Another thread is loading, wait
            for _ in range(100):
                time.sleep(0.1)
                if self._model_loaded:
                    return True
            return False

        self._model_loading = True
        try:
            from sentence_transformers import SentenceTransformer
            print(f"[VectorMemory] Loading embedding model: {_MODEL_NAME}...")
            t0 = time.time()
            self._model = SentenceTransformer(_MODEL_NAME)
            elapsed = time.time() - t0
            print(f"[VectorMemory] Model loaded in {elapsed:.1f}s")
            self._model_loaded = True
            return True
        except ImportError:
            print("[VectorMemory] sentence-transformers not installed. "
                  "Run: pip install sentence-transformers")
            return False
        except Exception as e:
            print(f"[VectorMemory] Failed to load model: {e}")
            return False
        finally:
            self._model_loading = False

    # ── Embedding ───────────────────────────────────────────────────────

    def _embed(self, texts: List[str]) -> Optional[np.ndarray]:
        """Embed a list of texts into dense vectors."""
        if not self._ensure_model():
            return None
        try:
            vectors = self._model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return vectors.astype(np.float32)
        except Exception as e:
            print(f"[VectorMemory] Embedding error: {e}")
            return None

    def _embed_single(self, text: str) -> Optional[np.ndarray]:
        """Embed a single text."""
        if not self._ensure_model():
            return None
        try:
            vector = self._model.encode(
                [text],
                normalize_embeddings=True,
            )
            return vector[0].astype(np.float32)
        except Exception as e:
            print(f"[VectorMemory] Embedding error: {e}")
            return None

    # ── Indexing ────────────────────────────────────────────────────────

    def index_all_stores(self) -> int:
        """
        Index all memory stores for semantic search.
        Returns number of entries indexed.
        """
        entries = []

        # 1. Neural memory (brain/neural_memory.py)
        try:
            from brain.neural_memory import get_brain
            brain = get_brain()
            for cat_name, cat_entries in brain.all_memories().items():
                for entry in cat_entries:
                    text = f"{entry.get('key', '')}: {entry.get('value', '')}"
                    entries.append({
                        "id": entry.get("memory_id", f"{cat_name}:{entry.get('key', '')}"),
                        "text": text,
                        "source": "neural",
                        "category": cat_name,
                        "strength": entry.get("strength", 5.0),
                        "created": entry.get("created", ""),
                    })
        except Exception as e:
            print(f"[VectorMemory] Neural store index error: {e}")

        # 2. Long-term memory (memory/memory_manager.py)
        try:
            from memory.memory_manager import load_memory
            lt_mem = load_memory()
            for cat_name, items in lt_mem.items():
                if not isinstance(items, dict):
                    continue
                for key, entry in items.items():
                    if isinstance(entry, dict) and "value" in entry:
                        text = f"{key}: {entry['value']}"
                        entries.append({
                            "id": f"lt:{cat_name}:{key}",
                            "text": text,
                            "source": "long_term",
                            "category": cat_name,
                            "strength": 8.0,
                            "created": entry.get("updated", ""),
                        })
        except Exception as e:
            print(f"[VectorMemory] Long-term store index error: {e}")

        # 3. Episodic memory (brain/episodic_memory.py)
        try:
            from brain.episodic_memory import get_episodic_memory
            ep = get_episodic_memory()
            for event in ep.get_recent_events(limit=200):
                text = f"{event.get('type', '')}: {event.get('content', '')}"
                entries.append({
                    "id": event.get("event_id", ""),
                    "text": text,
                    "source": "episodic",
                    "category": event.get("type", "event"),
                    "strength": event.get("strength", 5.0),
                    "created": event.get("timestamp", ""),
                })
        except Exception:
            pass  # Episodic memory may not exist yet

        # 4. Learnings (brain/learning.py)
        try:
            from brain.learning import get_learning_engine
            engine = get_learning_engine()
            for event in engine.get_recent_learnings(50):
                data = event.get("data", {})
                text = f"{event.get('type', '')}: {data.get('tool', '')} {data.get('context', '')} {data.get('error', '')}"
                entries.append({
                    "id": event.get("id", ""),
                    "text": text,
                    "source": "learning",
                    "category": event.get("type", "learning"),
                    "strength": 6.0,
                    "created": event.get("timestamp", ""),
                })
        except Exception:
            pass

        if not entries:
            print("[VectorMemory] No entries to index")
            return 0

        # Embed all texts
        texts = [e["text"] for e in entries]
        vectors = self._embed(texts)
        if vectors is None:
            return 0

        with self._lock:
            self._entries = entries
            self._vectors = vectors

        self._save_index()
        print(f"[VectorMemory] Indexed {len(entries)} entries from "
              f"{len(set(e['source'] for e in entries))} stores")
        return len(entries)

    def index_single(self, entry_id: str, text: str, source: str = "neural",
                     category: str = "", strength: float = 5.0):
        """Add or update a single entry in the index."""
        vector = self._embed_single(text)
        if vector is None:
            return

        with self._lock:
            # Check if entry already exists
            for i, entry in enumerate(self._entries):
                if entry["id"] == entry_id:
                    self._entries[i]["text"] = text
                    self._entries[i]["strength"] = strength
                    self._vectors[i] = vector
                    return

            # New entry
            self._entries.append({
                "id": entry_id,
                "text": text,
                "source": source,
                "category": category,
                "strength": strength,
                "created": datetime.now().isoformat(),
            })
            if self._vectors is None:
                self._vectors = vector.reshape(1, -1)
            else:
                self._vectors = np.vstack([self._vectors, vector.reshape(1, -1)])

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5,
               source_filter: Optional[str] = None,
               min_similarity: float = 0.3) -> List[dict]:
        """
        Semantic search over all indexed memories.

        Args:
            query: Natural language query
            top_k: Number of results to return
            source_filter: Filter by source ("neural", "long_term", "episodic", "learning")
            min_similarity: Minimum cosine similarity threshold

        Returns:
            List of dicts with id, text, source, similarity, metadata
        """
        if self._vectors is None or len(self._entries) == 0:
            return []

        vector = self._embed_single(query)
        if vector is None:
            # Fallback to keyword search
            return self._keyword_search(query, top_k, source_filter)

        # Cosine similarity (vectors are already normalized)
        with self._lock:
            if self._vectors is None or len(self._vectors) == 0:
                return []
            similarities = self._vectors @ vector

        # Build results
        results = []
        for i, (entry, sim) in enumerate(zip(self._entries, similarities)):
            if sim < min_similarity:
                continue
            if source_filter and entry.get("source") != source_filter:
                continue
            results.append({
                "id": entry["id"],
                "text": entry["text"],
                "source": entry["source"],
                "category": entry.get("category", ""),
                "similarity": float(sim),
                "strength": entry.get("strength", 5.0),
                "created": entry.get("created", ""),
            })

        # Sort by similarity * strength (hybrid scoring)
        results.sort(
            key=lambda r: r["similarity"] * 0.7 + (r["strength"] / 10.0) * 0.3,
            reverse=True,
        )
        return results[:top_k]

    def _keyword_search(self, query: str, top_k: int,
                        source_filter: Optional[str]) -> List[dict]:
        """Fallback keyword search when embeddings aren't available."""
        q = query.lower()
        results = []
        with self._lock:
            for entry in self._entries:
                if source_filter and entry.get("source") != source_filter:
                    continue
                text = entry.get("text", "").lower()
                score = 0
                if q in text:
                    score = 1
                for word in q.split():
                    if len(word) > 3 and word in text:
                        score += 0.5
                if score > 0:
                    results.append({
                        "id": entry["id"],
                        "text": entry["text"],
                        "source": entry["source"],
                        "category": entry.get("category", ""),
                        "similarity": score,
                        "strength": entry.get("strength", 5.0),
                        "created": entry.get("created", ""),
                    })
        results.sort(key=lambda r: r["similarity"], reverse=True)
        return results[:top_k]

    # ── Persistence ─────────────────────────────────────────────────────

    def _save_index(self):
        """Save index metadata and vectors to disk."""
        try:
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)

            # Save metadata
            meta = {
                "entries": self._entries,
                "model": _MODEL_NAME,
                "dim": _EMBEDDING_DIM,
                "indexed_at": datetime.now().isoformat(),
                "count": len(self._entries),
            }
            INDEX_FILE.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Save vectors
            if self._vectors is not None:
                np.savez_compressed(str(EMBEDDINGS_FILE), vectors=self._vectors)

        except Exception as e:
            print(f"[VectorMemory] Save error: {e}")

    def _load_index(self):
        """Load cached index from disk."""
        if not INDEX_FILE.exists():
            return
        try:
            meta = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            self._entries = meta.get("entries", [])

            if EMBEDDINGS_FILE.exists() and self._entries:
                data = np.load(str(EMBEDDINGS_FILE))
                self._vectors = data["vectors"]
                if len(self._vectors) != len(self._entries):
                    # Mismatch — invalidate
                    self._entries = []
                    self._vectors = None
                    print("[VectorMemory] Index/vectors mismatch — cleared")
                else:
                    print(f"[VectorMemory] Loaded {len(self._entries)} cached vectors")
        except Exception as e:
            print(f"[VectorMemory] Load error: {e}")
            self._entries = []
            self._vectors = None

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get vector memory statistics."""
        with self._lock:
            sources = {}
            for entry in self._entries:
                src = entry.get("source", "unknown")
                sources[src] = sources.get(src, 0) + 1

            return {
                "total_entries": len(self._entries),
                "model_loaded": self._model_loaded,
                "model_name": _MODEL_NAME,
                "embedding_dim": _EMBEDDING_DIM,
                "sources": sources,
                "has_vectors": self._vectors is not None,
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format vector memory stats for system prompt."""
        stats = self.get_stats()
        if stats["total_entries"] == 0:
            return ""

        parts = [
            "[VECTOR MEMORY — Semantic search over all memories]",
            f"Indexed: {stats['total_entries']} entries | "
            f"Model: {stats['model_name']}",
        ]
        if stats["sources"]:
            src_str = ", ".join(f"{k}:{v}" for k, v in stats["sources"].items())
            parts.append(f"Sources: {src_str}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────

_vector_memory = None
_vector_memory_lock = threading.Lock()


def get_vector_memory() -> VectorMemory:
    """Get the singleton vector memory instance."""
    global _vector_memory
    if _vector_memory is None:
        with _vector_memory_lock:
            if _vector_memory is None:
                _vector_memory = VectorMemory()
    return _vector_memory
