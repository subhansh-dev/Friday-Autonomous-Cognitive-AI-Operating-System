import json
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# [FIX-4] Cached client and config
_config_cache: dict | None = None
_client_instance = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            _config_cache = json.loads(
                API_CONFIG_PATH.read_text(encoding="utf-8")
            )
        except Exception:
            _config_cache = {}
    return _config_cache


# [FIX-3] Error handling for missing key
def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found in config/api_keys.json")
    return key


# [FIX-4] Cached client
def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


# [FIX-7] Max query length
_MAX_QUERY_LEN = 2000


def _gemini_search(query: str) -> str:
    from google.genai import types

    # [FIX-7] Truncate long queries
    if len(query) > _MAX_QUERY_LEN:
        query = query[:_MAX_QUERY_LEN] + "..."

    client   = _get_client()  # [FIX-4] Cached
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    # [FIX-1] Safely handle empty candidates
    if not response.candidates:
        raise ValueError("Gemini returned no candidates (possibly filtered).")

    text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text

    text = text.strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


# [FIX-2] Proper import with clear error
_DDG_AVAILABLE = False
try:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    _DDG_AVAILABLE = True
except ImportError:
    DDGS = None


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    if not _DDG_AVAILABLE:
        raise RuntimeError(
            "DuckDuckGo search not installed. "
            "Run: pip install duckduckgo-search"
        )

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   r.get("title",  ""),
                "snippet": r.get("body",   ""),
                "url":     r.get("href",   ""),
            })
    return results


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        title   = r.get("title", "").strip()
        snippet = r.get("snippet", "").strip()
        url     = r.get("url", "").strip()

        # [FIX-8] Skip completely empty results
        if not title and not snippet and not url:
            continue

        if title:
            lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
        if url:
            lines.append(f"   {url}")
        lines.append("")

    # [FIX-8] Check we actually have content beyond the header
    if len(lines) <= 2:
        return f"No usable results found for: {query}"

    return "\n".join(lines).strip()


def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compare {', '.join(items)} in terms of {aspect}. "
        "Give specific facts and data."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        print(f"[WebSearch] Gemini compare failed: {e} — falling back to DDG")

    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception as e:
            # [FIX-5] Report which items failed
            print(f"[WebSearch] DDG failed for '{item}': {e}")
            all_results[item] = []

    lines = [f"Comparison — {aspect.upper()}", "-" * 40]
    for item in items:
        lines.append(f"\n> {item}")
        item_results = all_results.get(item, [])
        if not item_results:
            lines.append("  (no data found)")
            continue
        for r in item_results[:2]:
            if r.get("snippet"):
                lines.append(f"  - {r['snippet']}")
    return "\n".join(lines)


# [FIX-6] Store search in session memory
def _store_search(session_memory, query: str, result: str) -> None:
    if not session_memory:
        return
    try:
        if hasattr(session_memory, "set_last_search"):
            session_memory.set_last_search(query=query, response=result[:200])
    except Exception:
        pass


def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query  = params.get("query", "").strip()
    mode   = params.get("mode",  "search").lower().strip()
    items  = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"

    if not query and not items:
        return "Please provide a search query."

    if items and mode != "compare":
        mode = "compare"

    if player:
        player.write_log(f"[Search] {query or ', '.join(items)}")

    print(f"[WebSearch] Query: {query!r}  Mode: {mode}")

    try:
        if mode == "compare" and items:
            print(f"[WebSearch] Comparing: {items}")
            result = _compare(items, aspect)
            print("[WebSearch] Compare done.")
            _store_search(session_memory, f"compare: {', '.join(items)}", result)
            return result

        print("[WebSearch] Trying Gemini...")
        try:
            result = _gemini_search(query)
            print("[WebSearch] Gemini OK.")
            _store_search(session_memory, query, result)
            return result
        except Exception as e:
            print(f"[WebSearch] Gemini failed ({e}) — trying DDG...")
            results = _ddg_search(query)
            result  = _format_ddg(query, results)
            print(f"[WebSearch] DDG: {len(results)} result(s).")
            _store_search(session_memory, query, result)
            return result

    except Exception as e:
        print(f"[WebSearch] All backends failed: {e}")
        return f"Search failed: {e}"
