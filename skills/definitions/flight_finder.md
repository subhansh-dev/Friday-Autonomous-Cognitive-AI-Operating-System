---
name: flight_finder
trigger: When the user wants to search for flights
freedom: medium
gotchas:
  - Uses Google Flights scraping — results depend on availability
  - Prices change frequently — treat as estimates
  - May need to handle CAPTCHAs
---

origin: string — airport code (JFK) or city
destination: string — airport code or city
date: string — YYYY-MM-DD format
Returns: available flights with prices, airlines, duration, stops