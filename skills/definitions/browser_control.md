---
name: browser_control
trigger: When the user wants to navigate websites, fill forms, take screenshots of web pages, or automate browser actions
freedom: medium
gotchas:
  - Playwright must be installed: pip install playwright && playwright install chromium
  - Some sites block automation via detection scripts
  - Headless mode may miss visually-dependent features
---

Actions: navigate, screenshot, fill_form, click, scrape, get_html
Use playwright.sync_playwright() for blocking operations, async for concurrent tasks.
Handle exceptions gracefully — sites change DOM often.