---
name: weather_report
trigger: When the user asks about weather conditions or forecast
freedom: high
gotchas:
  - Uses DuckDuckGo — may not always have current data
  - Location must be specific: "London, UK" not just "London"
  - Forecasts are general, not minute-by-minute
---

Location: string — city name, optionally with country
Returns: current temp, conditions, humidity, wind, 3-day forecast
Cache results for 30 minutes to avoid repeated API calls.