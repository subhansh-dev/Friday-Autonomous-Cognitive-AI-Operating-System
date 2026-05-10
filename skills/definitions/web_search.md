---
name: web_search
trigger: When the user wants to search the web for information
freedom: high
gotchas:
  - Uses DuckDuckGo — results depend on their API availability
  - Rate limited — don't spam queries
  - May not return full article content
---

Query: string — search terms, max 200 chars
Returns: list of {title, url, snippet} dicts
Use for quick factual lookups, not deep research.