"""
ai_pipeline.py — AI Pipeline for Friday

Multi-step AI workflows: summarization, translation, sentiment analysis,
entity extraction, and document processing.
"""

import sys
import json
import re
import logging
from pathlib import Path

# [FIX-3] LangChain flags exist but were never used — kept for future use
_HAVE_LANGCHAIN = False
try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain.chains import LLMChain
    _HAVE_LANGCHAIN = True
except ImportError:
    pass

_HAVE_LANGGRAPH = False
try:
    from langgraph.graph import StateGraph, END
    from typing import TypedDict, Literal
    _HAVE_LANGGRAPH = True
except ImportError:
    pass

log = logging.getLogger("ai_pipeline")


def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# ── [FIX-1] + [FIX-2] + [FIX-10] Cached client with configurable model ─────

_client_instance = None
GEMINI_MODEL = "gemini-2.5-flash"


def _get_api_key() -> str:
    cfg_path = _get_base_dir() / "config" / "api_keys.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))["gemini_api_key"]


def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


def _generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    """Central generation call — uses cached client."""
    client = _get_client()
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


# ── [FIX-6] Robust JSON extraction from LLM responses ──────────────────────

def _extract_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences and noise."""
    text = text.strip()

    # Try to strip markdown fences first
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Find the outermost { ... }
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1  # keep looking

    # Last resort: try the whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── [FIX-7] + [FIX-9] Truncation with warnings ─────────────────────────────

def _truncate(text: str, max_chars: int, label: str = "input") -> tuple[str, bool]:
    """Truncate text and return (truncated_text, was_truncated)."""
    if len(text) <= max_chars:
        return text, False
    log.warning(f"[Pipeline] {label} truncated from {len(text)} to {max_chars} chars")
    return text[:max_chars], True


# ── Summarization ───────────────────────────────────────────────────────────

def summarize_text(text: str, max_length: int = 200, language: str = "english") -> str:
    """Summarize text using Gemini with fallback."""
    if not text or not text.strip():
        return "(empty text)"

    # [FIX-13] Validate max_length
    max_length = max(20, min(max_length, 2000))

    if len(text.split()) <= max_length:
        return text

    text_truncated, was_trunc = _truncate(text, 8000, "summarize input")

    try:
        trunc_note = " (Note: input was truncated)" if was_trunc else ""
        prompt = (
            f"Summarize the following {language} text in {max_length} words or less. "
            f"Be concise and capture the key points.{trunc_note}\n\n{text_truncated}"
        )
        result = _generate(prompt)
        return result[:2000]
    except Exception as e:
        log.warning(f"[Pipeline] Summarize API failed: {e}, using fallback")
        return _fallback_summary(text, max_length)


def _fallback_summary(text: str, max_length: int = 200) -> str:
    """Fallback summarizer when API is unavailable."""
    words = text.split()
    if len(words) <= max_length:
        return text

    paragraphs = text.split('\n')
    summary_parts = []
    for p in paragraphs:
        # [FIX-11] Split on sentence-ending period + space, not just "."
        sentences = re.split(r'(?<=[.!?])\s+', p.strip())
        for s in sentences:
            s = s.strip()
            if len(s) > 20:
                summary_parts.append(s)
                break  # one sentence per paragraph

    result = ' '.join(summary_parts[:5])
    result_words = result.split()
    if len(result_words) > max_length:
        result = ' '.join(result_words[:max_length]) + '...'
    return result or ' '.join(words[:max_length]) + '...'


# ── Sentiment Analysis ──────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> str:
    """Analyze sentiment of text."""
    if not text or not text.strip():
        return "(empty text)"

    text_truncated, was_trunc = _truncate(text, 3000, "sentiment input")

    try:
        trunc_note = " (Note: input was truncated)" if was_trunc else ""
        prompt = (
            f"Analyze the sentiment of the following text.{trunc_note}\n"
            f"Respond ONLY with a JSON object:\n"
            f'{{"sentiment": "positive|negative|neutral", '
            f'"confidence": 0.0-1.0, '
            f'"key_emotion": "word", '
            f'"brief_reason": "one sentence"}}\n\n'
            f"Text: {text_truncated}"
        )
        resp_text = _generate(prompt)

        # [FIX-6] Robust JSON extraction
        data = _extract_json(resp_text)
        if data:
            sentiment = data.get('sentiment', 'unknown')
            confidence = data.get('confidence', 0)
            emotion = data.get('key_emotion', 'N/A')
            reason = data.get('brief_reason', '')
            result = f"Sentiment: {sentiment} (confidence: {confidence:.2f})\nEmotion: {emotion}"
            if reason:
                result += f"\nReason: {reason}"
            return result
        return resp_text[:200]
    except Exception as e:
        return f"Sentiment analysis unavailable: {e}"


# ── Entity Extraction ───────────────────────────────────────────────────────

def extract_entities(text: str) -> str:
    """Extract named entities from text."""
    if not text or not text.strip():
        return "(empty text)"

    text_truncated, was_trunc = _truncate(text, 3000, "entity input")

    try:
        trunc_note = " (Note: input was truncated)" if was_trunc else ""
        prompt = (
            f"Extract named entities from the text below.{trunc_note}\n"
            f"Respond ONLY with a JSON object:\n"
            f'{{"people": ["name1"], "places": ["place1"], '
            f'"organizations": ["org1"], "dates": ["date1"], '
            f'"key_concepts": ["concept1"]}}\n\n'
            f"Text: {text_truncated}"
        )
        resp_text = _generate(prompt)

        # [FIX-6] Robust JSON extraction
        data = _extract_json(resp_text)
        if data:
            lines = []
            for k, v in data.items():
                if v and isinstance(v, list):
                    lines.append(f"{k.replace('_', ' ').title()}: {', '.join(str(x) for x in v[:5])}")
            return '\n'.join(lines) if lines else 'No entities found.'
        return resp_text[:200]
    except Exception as e:
        return f"Entity extraction unavailable: {e}"


# ── Translation ─────────────────────────────────────────────────────────────

def translate_text(text: str, target_language: str = "English") -> str:
    """Translate text to target language."""
    if not text or not text.strip():
        return "(empty text)"

    text_truncated, was_trunc = _truncate(text, 4000, "translate input")

    try:
        trunc_note = " (Note: input was truncated — partial translation)" if was_trunc else ""
        prompt = (
            f"Translate the following text to {target_language}. "
            f"Respond with ONLY the translation, no explanations.{trunc_note}\n\n"
            f"{text_truncated}"
        )
        result = _generate(prompt)
        return result[:3000]
    except Exception as e:
        return f"Translation error: {e}"


# ── Rich Formatting ─────────────────────────────────────────────────────────

def format_with_rich(data_json: str, format_type: str = "table") -> str:
    """Format data using Rich library for beautiful console output."""
    try:
        from brain.integrations import rich_format
        data = json.loads(data_json) if isinstance(data_json, str) else data_json
        title = 'Results'
        if isinstance(data, dict):
            title = data.pop('_title', 'Results')
        return rich_format(title, data, format_type)
    except ImportError:
        return "Rich library not available."
    except Exception as e:
        return f"Rich formatting error: {e}"


# ── [FIX-4] + [FIX-9] + [FIX-12] Document Processing ───────────────────────

SUPPORTED_TEXT_EXTENSIONS = {
    '.txt', '.md', '.markdown', '.csv', '.json', '.xml',
    '.html', '.htm', '.py', '.js', '.ts', '.java', '.c',
    '.cpp', '.h', '.css', '.yaml', '.yml', '.toml', '.ini',
    '.cfg', '.conf', '.log', '.sql', '.sh', '.bat', '.ps1',
    '.rst', '.tex', '.rtf',
}

BINARY_EXTENSIONS = {
    '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.zip',
    '.tar', '.gz', '.rar', '.7z', '.exe', '.dll', '.so',
}


def _read_document(filepath: str) -> tuple[str, str]:
    """Read a document file, with type detection. Returns (content, error)."""
    p = Path(filepath).expanduser()
    if not p.exists():
        return "", f"File not found: {filepath}"

    ext = p.suffix.lower()

    # [FIX-4] Reject known binary formats
    if ext in BINARY_EXTENSIONS:
        if ext == '.csv':
            pass  # CSV is text, fall through
        else:
            return "", (
                f"Binary file format ({ext}) cannot be read as text. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_TEXT_EXTENSIONS))}"
            )

    # [FIX-4] Check for binary content even in unknown extensions
    try:
        chunk = p.read_bytes()[:4096]
        if b'\x00' in chunk and ext not in SUPPORTED_TEXT_EXTENSIONS:
            return "", f"Binary file detected: {filepath}. Cannot process as text."
    except Exception:
        pass

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return "", f"File is empty: {filepath}"
        return content, ""
    except Exception as e:
        return "", f"Could not read file: {e}"


# [FIX-12] CSV-aware processing
def _summarize_csv(content: str, max_length: int = 200) -> str:
    """Summarize CSV data with row/column stats + sample rows."""
    lines = content.strip().split('\n')
    if not lines:
        return "(empty CSV)"

    headers = lines[0].split(',')
    num_rows = len(lines) - 1
    num_cols = len(headers)

    sample_rows = min(5, num_rows)
    sample = '\n'.join(lines[:sample_rows + 1])

    summary = f"CSV with {num_rows} rows and {num_cols} columns.\n"
    summary += f"Columns: {', '.join(h.strip() for h in headers)}\n\n"
    summary += f"First {sample_rows} rows:\n{sample}"

    # If small enough, just return the stats + sample
    if len(content) < 3000:
        return summary

    # For large CSVs, also get an AI summary
    try:
        ai_summary = summarize_text(
            f"Column names: {', '.join(headers)}\n\nSample data:\n{sample}",
            max_length=max_length
        )
        summary += f"\n\nAI Summary:\n{ai_summary}"
    except Exception:
        pass

    return summary


def _summarize_json(content: str, max_length: int = 200) -> str:
    """Summarize JSON data with structure info."""
    try:
        data = json.loads(content)
        if isinstance(data, list):
            summary = f"JSON array with {len(data)} items."
            if data:
                summary += f"\nFirst item keys: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0]).__name__}"
            return summary
        elif isinstance(data, dict):
            keys = list(data.keys())
            summary = f"JSON object with {len(keys)} keys: {', '.join(str(k) for k in keys[:10])}"
            if len(keys) > 10:
                summary += f" ... and {len(keys) - 10} more"
            return summary
        return f"JSON value: {type(data).__name__}"
    except json.JSONDecodeError:
        return _fallback_summary(content, max_length)


def process_document(filepath: str, operation: str = "summarize", **kwargs) -> str:
    """Process a document file with the specified operation."""
    content, err = _read_document(filepath)
    if err:
        return err

    ext = Path(filepath).suffix.lower()

    if operation == "summarize":
        max_len = max(20, int(kwargs.get('max_length', 200)))

        # [FIX-12] Format-aware summarization
        if ext == '.csv':
            return _summarize_csv(content, max_len)
        elif ext == '.json':
            return _summarize_json(content, max_len)
        else:
            return summarize_text(content, max_length=max_len)

    elif operation == "sentiment":
        return analyze_sentiment(content)

    elif operation == "entities":
        return extract_entities(content)

    elif operation == "translate":
        lang = kwargs.get('language', 'English')
        return translate_text(content, lang)

    else:
        return f"Unknown operation: '{operation}'. Use: summarize, sentiment, entities, translate"
