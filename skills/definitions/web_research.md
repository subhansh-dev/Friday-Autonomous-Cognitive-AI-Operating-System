---
name: web_research
trigger: When the user wants deep research on a topic using multiple web sources
freedom: high
gotchas:
  - Results depend on web availability — handle offline gracefully
  - May take time for comprehensive research
  - Source quality varies — prioritize authoritative sources
---

topic: string — research question or topic
depth: "quick", "standard", "deep" — how thorough to be
Uses multiple sources, synthesizes findings into report.
Output: markdown report with citations.