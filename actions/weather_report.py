import webbrowser
import json
from urllib.parse import quote_plus


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"FRIDAY: {message}")
        except Exception:
            pass


def _try_fetch_weather(city: str) -> str | None:
    """Attempt to get weather data from wttr.in (no API key needed)."""
    try:
        import urllib.request
        url = f"https://wttr.in/{city}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        current = data.get("current_condition", [{}])[0]
        desc    = current.get("weatherDesc", [{}])[0].get("value", "")
        temp_c  = current.get("temp_C", "?")
        feels   = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")
        wind    = current.get("windspeedKmph", "?")
        uv      = current.get("uvIndex", "?")
        visibility = current.get("visibility", "?")
        pressure = current.get("pressure", "?")
        return (f"{desc}, {temp_c}°C (feels like {feels}°C), "
                f"humidity {humidity}%, wind {wind} km/h, "
                f"UV index {uv}, visibility {visibility} km, "
                f"pressure {pressure} hPa.")
    except Exception:
        return None


def _try_fetch_forecast(city: str, days: int = 3) -> str | None:
    """Attempt to get multi-day forecast from wttr.in."""
    try:
        import urllib.request
        url = f"https://wttr.in/{city}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        weather_list = data.get("weather", [])
        if not weather_list:
            return None

        lines = []
        for day in weather_list[:days]:
            date = day.get("date", "?")
            max_temp = day.get("maxtempC", "?")
            min_temp = day.get("mintempC", "?")
            desc = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "") if len(day.get("hourly", [])) > 4 else ""
            lines.append(f"  {date}: {min_temp}°C - {max_temp}°C, {desc}")

        return "\n".join(lines)
    except Exception:
        return None


def _try_fetch_air_quality(city: str) -> str | None:
    """Attempt to get air quality data."""
    try:
        import urllib.request
        url = f"https://wttr.in/{city}?format=%t+%C+%h+%w+%P+%u+%V"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read().decode("utf-8").strip()
        return data
    except Exception:
        return None


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city = parameters.get("city")
    when = parameters.get("time", "today")

    if not city or not isinstance(city, str) or not city.strip():
        msg = "Sir, the city is missing for the weather report."
        _log(msg, player)
        return msg

    city = city.strip()
    when = (when or "today").strip()

    # Build comprehensive weather report
    parts = []

    # Current conditions
    if when.lower() in ("today", "now", ""):
        current = _try_fetch_weather(city)
        if current:
            parts.append(f"Current weather in {city}: {current}")

        # Multi-day forecast
        forecast = _try_fetch_forecast(city, days=3)
        if forecast:
            parts.append(f"3-day forecast:\n{forecast}")

    search_query = f"weather in {city} {when}"
    url = f"https://www.google.com/search?q={quote_plus(search_query)}"

    try:
        webbrowser.open(url)
    except Exception as e:
        _log(f"Couldn't open browser: {e}", player)

    if parts:
        msg = " ".join(parts) + " Showing more details in the browser, sir."
    else:
        msg = f"Showing the weather for {city}, {when}, sir."

    _log(msg, player)

    if session_memory:
        try:
            if hasattr(session_memory, "set_last_search"):
                session_memory.set_last_search(query=search_query, response=msg)
        except Exception:
            pass

    return msg
