import sys
import json
import re
import asyncio
import urllib.parse
from pathlib import Path
from datetime import datetime

_HAVE_PLAYWRIGHT = False
try:
    from playwright.async_api import async_playwright
    _HAVE_PLAYWRIGHT = True
except ImportError:
    pass

_HAVE_BS4 = False
_HAVE_LXML = False
try:
    from bs4 import BeautifulSoup
    _HAVE_BS4 = True
    try:
        import lxml  # noqa: F401
        _HAVE_LXML = True
    except ImportError:
        pass
except ImportError:
    pass


def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _truncate_at_sentence(text: str, max_len: int = 500) -> str:
    """Truncate text at a sentence boundary, not mid-word."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # Find the last sentence-ending punctuation
    for sep in ('. ', '! ', '? '):
        idx = truncated.rfind(sep)
        if idx > max_len * 0.5:  # Don't truncate too aggressively
            return truncated[:idx + 1]
    # Fallback: last space
    idx = truncated.rfind(' ')
    if idx > max_len * 0.5:
        return truncated[:idx] + '...'
    return truncated + '...'


def _extract_links_bs4(html: str, max_results: int) -> list[tuple[str, str]]:
    """Extract search result links using BeautifulSoup."""
    parser = 'lxml' if _HAVE_LXML else 'html.parser'
    soup = BeautifulSoup(html, parser)
    links = []

    # Primary: Google's /url?q= pattern
    for a in soup.select('a[href^="/url?"]'):
        href = a.get('href', '')
        match = re.search(r'[?&]q=([^&]+)', href)
        if match:
            url = urllib.parse.unquote(match.group(1))  # [FIX-4]
            title_el = a.find('h3')
            title = title_el.get_text(strip=True) if title_el else ''
            if title and url and not url.startswith('https://google'):
                links.append((title, url))
                if len(links) >= max_results:
                    return links

    # Fallback: jsname attribute
    if not links:
        for a in soup.select('a[jsname]'):
            href = a.get('href', '')
            if href.startswith('http') and 'google' not in href:
                links.append((a.get_text(strip=True)[:60], href))
                if len(links) >= max_results:
                    break

    return links


def _extract_links_regex(html: str, max_results: int) -> list[tuple[str, str]]:
    """Fallback link extraction via regex."""
    links = []
    for match in re.finditer(r'href="/url\?q=([^"&]+)', html):
        url = urllib.parse.unquote(match.group(1))
        if url.startswith('http') and 'google' not in url:
            title_match = re.search(
                r'<h3[^>]*>([^<]+)</h3>',
                html[match.start():match.start() + 500]
            )
            title = title_match.group(1) if title_match else ''
            links.append((title, url))
            if len(links) >= max_results:
                break
    return links


async def _accept_consent(page) -> None:
    """Try to dismiss Google's cookie consent dialog."""
    try:
        # Common consent button selectors
        for selector in [
            'button:has-text("Accept all")',
            'button:has-text("I agree")',
            'button:has-text("Reject all")',
            '#L2AGLb',           # Google's "I agree" button ID
            'button[id*="agree"]',
        ]:
            btn = page.locator(selector)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1500)
                return
    except Exception:
        pass


async def _scrape_page_content(context, url: str) -> str:
    """Scrape and summarize a single page."""
    page = await context.new_page()
    try:
        await page.goto(url, timeout=12000, wait_until='domcontentloaded')
        await page.wait_for_timeout(1500)
        content_html = await page.content()

        if _HAVE_BS4:
            parser = 'lxml' if _HAVE_LXML else 'html.parser'
            soup = BeautifulSoup(content_html, parser)
            for tag in soup(['script', 'style', 'nav', 'footer',
                             'header', 'aside', 'iframe', 'noscript']):
                tag.decompose()
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text)
            return _truncate_at_sentence(text, 500)
        else:
            return f'(scraped {len(content_html)} bytes, install bs4 for extraction)'
    except Exception as e:
        return f'(scrape error: {str(e)[:80]})'
    finally:
        await page.close()


async def _research(query: str, depth: int, max_results: int) -> str:
    """Core async research function."""
    results_text = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            )
            page = await context.new_page()

            # Search Google
            search_url = (
                f'https://www.google.com/search'
                f'?q={urllib.parse.quote(query)}&num={max_results}'
            )
            try:
                await page.goto(search_url, timeout=15000,
                                wait_until='domcontentloaded')
                # [FIX-3] Handle consent dialog
                await _accept_consent(page)
                # [FIX-6] Wait for search results to appear
                try:
                    await page.wait_for_selector('h3', timeout=5000)
                except Exception:
                    await page.wait_for_timeout(2000)
                html = await page.content()
            except Exception as e:
                results_text.append(f'Search failed: {e}')
                await browser.close()
                return '\n'.join(results_text)

            # Extract links
            if _HAVE_BS4:
                links = _extract_links_bs4(html, max_results)
            else:
                links = _extract_links_regex(html, max_results)

            if not links:
                results_text.append('No search results found.')
                await browser.close()
                return '\n'.join(results_text)

            results_text.append(f'=== Research Results: {query} ===')

            for i, (title, url) in enumerate(links, 1):
                results_text.append(f'\n[{i}] {title}')
                results_text.append(f'    URL: {url}')

                # [FIX-5] Depth 2+: scrape page content
                if depth >= 2:
                    summary = await _scrape_page_content(context, url)
                    results_text.append(f'    Summary: {summary}')

            await browser.close()

        except Exception as e:
            # [FIX-5] Always close browser
            try:
                await browser.close()
            except Exception:
                pass
            results_text.append(f'Research error: {e}')

    return '\n'.join(results_text)


def web_research(parameters: dict, player=None) -> str:
    """Deep web research tool."""
    query = parameters.get('query', '')
    depth = int(parameters.get('depth', 1))
    max_results = max(1, min(int(parameters.get('max_results', 5)), 10))  # [FIX-7]

    if not query:
        return 'Query required.'

    if not _HAVE_PLAYWRIGHT:
        return 'Playwright not installed. Install with: pip install playwright'

    if player:
        player.write_log(f'WEB RESEARCH: researching {query}...')

    try:
        # [FIX-1] Use asyncio.run() safely
        # If an event loop is already running, we need to handle it
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (e.g., main.py's async context)
            # Run in a new thread with its own event loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _research(query, depth, max_results))
                result = future.result(timeout=60)
        else:
            result = asyncio.run(_research(query, depth, max_results))

        if player:
            player.write_log('WEB RESEARCH: completed')

        return result[:5000]

    except Exception as e:
        return f'Research error: {e}'
