import json
import re
import subprocess
import sys
import platform
import time as _time
from datetime import datetime, timedelta
from pathlib import Path

_OS = platform.system()

# [FIX-1] Removed broken import — use platform.system() directly
def _is_windows() -> bool: return _OS == "Windows"
def _is_mac()     -> bool: return _OS == "Darwin"
def _is_linux()   -> bool: return _OS == "Linux"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# [FIX-4] Cached config + client
_config_cache: dict | None = None
_client_instance = None
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_LITE  = "gemini-2.5-flash-lite"


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            _config_cache = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            _config_cache = {}
    return _config_cache


def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")


def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3,     "april": 4,
    "may": 5,     "june": 6,     "july": 7,       "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # Turkish months
    "ocak": 1,  "şubat": 2,  "mart": 3,   "nisan": 4,
    "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "eylül": 9, "ekim": 10,  "kasım": 11, "aralık": 12,
}

# [FIX-14] Extended relative date support
_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "pazartesi": 0, "salı": 1, "çarşamba": 2, "perşembe": 3,
    "cuma": 4, "cumartesi": 5, "pazar": 6,
}


# [FIX-3] + [FIX-14] Improved date parsing with better relative date support
def _parse_date(raw: str) -> str:
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    raw   = raw.strip()
    lower = raw.lower()
    today = datetime.now()

    # ISO format
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    # Common formats — try unambiguous first
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # US format (mm/dd/yyyy) — only if month > 12 is impossible
    try:
        parsed = datetime.strptime(raw, "%m/%d/%Y")
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Simple relative dates
    relative = {
        "today": today, "bugün": today,
        "tomorrow": today + timedelta(days=1),
        "yarın":    today + timedelta(days=1),
        "day after tomorrow": today + timedelta(days=2),
    }
    for key, val in relative.items():
        if key in lower:
            return val.strftime("%Y-%m-%d")

    # [FIX-14] "in N days/weeks" pattern
    in_match = re.search(r"in\s+(\d+)\s+(day|week|month)s?", lower)
    if in_match:
        n = int(in_match.group(1))
        unit = in_match.group(2)
        if unit == "day":
            return (today + timedelta(days=n)).strftime("%Y-%m-%d")
        elif unit == "week":
            return (today + timedelta(weeks=n)).strftime("%Y-%m-%d")
        elif unit == "month":
            # Approximate
            return (today + timedelta(days=n * 30)).strftime("%Y-%m-%d")

    # [FIX-14] "next weekday" pattern
    for day_name, day_num in _WEEKDAY_MAP.items():
        if day_name in lower:
            current_day = today.weekday()
            days_ahead = (day_num - current_day) % 7
            if days_ahead == 0:
                days_ahead = 7  # "next friday" means next week's friday
            if "next" in lower:
                days_ahead += 7 if days_ahead <= 7 else 0
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # [FIX-4] Gemini fallback with cached client
    try:
        client = _get_client()
        prompt = (
            f"Today is {today.strftime('%Y-%m-%d')} ({today.strftime('%A')}). "
            f"Convert this date expression to YYYY-MM-DD: '{raw}'. "
            f"Return ONLY the date string, nothing else."
        )
        response = client.models.generate_content(
            model=GEMINI_LITE, contents=prompt
        )
        result = (response.text or "").strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", result):
            return result
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini date parse failed: {e}")

    # Month name + day number fallback
    for month_name, month_num in _MONTH_MAP.items():
        if month_name in lower:
            # Find the number closest to the month name
            day_match = re.search(rf"{month_name}\s+(\d{{1,2}})", lower)
            if not day_match:
                day_match = re.search(r"(\d{1,2})\s+" + month_name, lower)
            if day_match:
                day = int(day_match.group(1))
                if 1 <= day <= 31:
                    year = today.year
                    # If the month has passed this year, use next year
                    if month_num < today.month or (
                        month_num == today.month and day < today.day
                    ):
                        year += 1
                    return f"{year}-{month_num:02d}-{day:02d}"

    # Last resort: today
    print(f"[FlightFinder] ⚠️ Could not parse date '{raw}' — using today.")
    return today.strftime("%Y-%m-%d")


_CABIN_CODE: dict[str, str] = {
    "economy":  "1",
    "premium":  "2",
    "business": "3",
    "first":    "4",
}


# [FIX-2] Proper Google Flights URL construction
def _build_google_flights_url(
    origin:      str,
    destination: str,
    date:        str,
    return_date: str | None = None,
    passengers:  int        = 1,
    cabin:       str        = "economy",
) -> str:
    """Build a Google Flights search URL.

    Uses the /travel/flights format that Google Flights accepts.
    The tfs parameter is a protobuf-encoded blob — we construct
    a search URL that works via the query parameter approach instead.
    """
    base = "https://www.google.com/travel/flights/search"

    # Build the search query
    params = [
        f"q=Flights+to+{destination}+from+{origin}+on+{date}",
    ]

    if return_date:
        params.append(f"tfs=CBwQAhoiEgoyMDI1LTAzLTE1agcIARID{origin}R2NIIARID{destination}")

    params.append(f"curr=USD")

    # Cabin class
    cabin_code = _CABIN_CODE.get(cabin.lower(), "1")
    params.append(f"cabin={cabin_code}")

    # Passengers
    if passengers > 1:
        params.append(f"adults={passengers}")

    url = base + "?" + "&".join(params)
    return url


# [FIX-5] + [FIX-6] Adaptive wait + error detection
def _search_flights_browser(
    origin:      str,
    destination: str,
    date:        str,
    return_date: str | None,
    passengers:  int,
    cabin:       str,
) -> tuple[str, str]:
    from actions.browser_control import browser_control

    url = _build_google_flights_url(
        origin, destination, date, return_date, passengers, cabin
    )

    print(f"[FlightFinder] 🌐 Opening: {url}")

    # Navigate to the page
    nav_result = browser_control({"action": "go_to", "url": url})

    # [FIX-6] Check if navigation succeeded
    if "error" in nav_result.lower() or "could not" in nav_result.lower():
        print(f"[FlightFinder] ⚠️ Navigation issue: {nav_result}")

    # [FIX-5] Adaptive wait — check if page loaded, wait longer if needed
    _time.sleep(3)  # Initial wait for dynamic content

    # Try to get page text — if it looks empty, wait and retry
    raw = browser_control({"action": "get_text"})

    if not raw or len(raw.strip()) < 100:
        print(f"[FlightFinder] Page seems empty, waiting longer...")
        _time.sleep(5)
        raw = browser_control({"action": "get_text"})

    # [FIX-6] Detect error responses from browser_control
    if raw and any(err in raw.lower() for err in [
        "could not start", "error", "not found", "timed out"
    ]):
        if len(raw) < 200:
            return ("", url)  # Treat as empty — don't send error text to Gemini

    return (raw or "", url)


def _parse_flights_with_gemini(
    raw_text:    str,
    origin:      str,
    destination: str,
    date:        str,
) -> list[dict]:
    if not raw_text or len(raw_text.strip()) < 50:
        print("[FlightFinder] ⚠️ Not enough text to parse")
        return []

    # [FIX-4] Cached client
    client = _get_client()

    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=(
            "You are a flight data extraction expert. "
            "Extract flight information from raw webpage text. "
            "Return ONLY valid JSON — no markdown, no explanation."
        ),
        response_mime_type="application/json"
    )

    prompt = (
        f"Extract flight options from {origin} to {destination} on {date} "
        f"from this Google Flights page text:\n\n{raw_text[:12000]}\n\n"
        f"Return a JSON array of up to 5 flights:\n"
        f'[{{"airline":"...","departure":"HH:MM","arrival":"HH:MM",'
        f'"duration":"Xh Ym","stops":0,"price":"...","currency":"USD"}}]\n'
        f"If no flights found, return: []"
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt, config=config
        )
        text    = (response.text or "").strip()
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        flights = json.loads(text)
        return flights if isinstance(flights, list) else []
    except json.JSONDecodeError as e:
        print(f"[FlightFinder] ⚠️ Gemini returned invalid JSON: {e}")
        return []
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini parse failed: {e}")
        return []


# [FIX-8] Robust price parsing
def _extract_price_num(price_str: str) -> int:
    """Extract numeric price value. Returns 999999 on failure."""
    if not price_str:
        return 999999
    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[^\d.,]", "", str(price_str))
    if not cleaned:
        return 999999
    # Handle European format (1.299) vs US format (1,299)
    # If both . and , exist, the last one is the decimal separator
    if "," in cleaned and "." in cleaned:
        if cleaned.rindex(",") > cleaned.rindex("."):
            # European: 1.299,99
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: 1,299.99
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Could be European thousands (1,299) or US decimal (1.5)
        parts = cleaned.split(",")
        if len(parts[-1]) == 3:
            # Thousands separator: 1,299
            cleaned = cleaned.replace(",", "")
        # else: leave as-is (will fail gracefully)
    try:
        return int(float(cleaned))
    except (ValueError, OverflowError):
        return 999999


def _format_spoken(
    flights:     list[dict],
    origin:      str,
    destination: str,
    date:        str,
) -> str:
    if not flights:
        return (
            f"I'm sorry Sir, I couldn't find any flights from {origin} to {destination} "
            f"on {date}. The page may not have loaded correctly."
        )

    lines = [
        f"Scanning the skies for you, Boss. Here are the top flights "
        f"from {origin} to {destination} on {date}."
    ]

    for i, f in enumerate(flights[:5], 1):
        airline   = f.get("airline",   "Unknown airline")
        departure = f.get("departure", "--:--")
        arrival   = f.get("arrival",   "--:--")
        duration  = f.get("duration",  "")
        stops     = f.get("stops",     0)
        price     = f.get("price",     "")
        currency  = f.get("currency",  "")

        stop_str  = "non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
        price_str = f"{price} {currency}".strip() if price else "price unavailable"
        dur_str   = f", {duration}" if duration else ""

        lines.append(
            f"Option {i}: {airline}, departing {departure}, "
            f"arriving {arrival}{dur_str}, {stop_str}, {price_str}."
        )

    # [FIX-8] Robust cheapest price comparison
    priced = [f for f in flights if f.get("price")]
    if priced:
        cheapest = min(priced, key=lambda x: _extract_price_num(x["price"]))
        lines.append(
            f"The cheapest option is {cheapest.get('airline')} "
            f"at {cheapest.get('price')} {cheapest.get('currency', '')}."
        )

    return " ".join(lines) + " Everything is grand."


def _format_text_report(
    flights:     list[dict],
    origin:      str,
    destination: str,
    date:        str,
    return_date: str | None,
    page_url:    str,
) -> str:
    lines = [
        "FRIDAY — Flight Search Results",
        "─" * 50,
        f"Route     : {origin} → {destination}",
        f"Date      : {date}",
    ]
    if return_date:
        lines.append(f"Return    : {return_date}")
    lines += [
        f"Searched  : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Source    : {page_url}",
        "─" * 50,
        "",
    ]

    if not flights:
        lines.append("No flights found.")
    else:
        for i, f in enumerate(flights, 1):
            stops    = f.get("stops", 0)
            stop_str = "Non-stop" if stops == 0 else f"{stops} stop(s)"
            lines += [
                f"Flight {i}:",
                f"  Airline   : {f.get('airline',   'N/A')}",
                f"  Departure : {f.get('departure', 'N/A')}",
                f"  Arrival   : {f.get('arrival',   'N/A')}",
                f"  Duration  : {f.get('duration',  'N/A')}",
                f"  Stops     : {stop_str}",
                f"  Price     : {f.get('price', 'N/A')} {f.get('currency', '')}",
                "",
            ]

    return "\n".join(lines)


# [FIX-10] Use platform detection instead of broken import
def _save_to_desktop(content: str, origin: str, destination: str) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"flights_{origin}_{destination}_{ts}.txt".replace(" ", "_")
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    filepath.write_text(content, encoding="utf-8")
    print(f"[FlightFinder] 💾 Saved: {filepath}")

    try:
        if _is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif _is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Could not open text editor: {e}")

    return str(filepath)


# [FIX-11] Accept speak as a keyword argument
def flight_finder(parameters: dict, player=None, speak=None, **kwargs) -> str:
    params = parameters or {}

    origin      = params.get("origin",      "").strip()
    destination = params.get("destination", "").strip()
    date_raw    = params.get("date",        "").strip()
    return_raw  = (params.get("return_date") or "").strip()
    cabin       = params.get("cabin", "economy").strip().lower()
    save        = bool(params.get("save", False))

    # [FIX-7] Robust passengers parsing
    try:
        passengers = max(1, min(int(params.get("passengers", 1)), 9))
    except (ValueError, TypeError):
        passengers = 1

    if not origin or not destination:
        return "Please provide both origin and destination, sir."
    if not date_raw:
        return "Please provide a departure date, sir."

    # Normalise cabin value
    if cabin not in _CABIN_CODE:
        cabin = "economy"

    date        = _parse_date(date_raw)
    return_date = _parse_date(return_raw) if return_raw else None

    if player:
        player.write_log(f"[FlightFinder] {origin} → {destination} on {date}")

    if speak:
        speak(f"Searching flights from {origin} to {destination} on {date}, sir.")

    print(
        f"[FlightFinder] ▶️ {origin} → {destination} | {date}"
        f"{' → ' + return_date if return_date else ''}"
        f" | {cabin} | {passengers} pax"
    )

    try:
        raw_text, page_url = _search_flights_browser(
            origin, destination, date, return_date, passengers, cabin
        )

        if not raw_text:
            return (
                "Could not retrieve flight data, sir. "
                "The page may not have loaded or the search returned no results."
            )

        if speak:
            speak("Analysing the results now, sir.")

        flights = _parse_flights_with_gemini(raw_text, origin, destination, date)
        spoken  = _format_spoken(flights, origin, destination, date)

        if speak:
            speak(spoken)

        result = spoken

        if save and flights:
            report     = _format_text_report(
                flights, origin, destination, date, return_date, page_url
            )
            saved_path = _save_to_desktop(report, origin, destination)
            result    += f" Results saved to Desktop: {saved_path}"

        return result

    except Exception as e:
        print(f"[FlightFinder] ❌ {e}")
        return f"Flight search failed: {e}"
