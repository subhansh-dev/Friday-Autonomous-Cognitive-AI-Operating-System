import asyncio
from playwright.async_api import async_playwright
import os
from datetime import datetime

class DeepDiveAgent:
    def __init__(self, output_dir="research_reports"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    async def research_topic(self, query, max_sources=5):
        print(f"Sensing... Starting Deep-Dive on: {query}")
        results = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(search_url)
            
            links = await page.locator("a").evaluate_all("els => els.map(el => el.href)")
            filtered_links = [l for l in links if "google.com" not in l and l.startswith("http")]
            
            for link in filtered_links[:max_sources]:
                try:
                    await page.goto(link, timeout=15000)
                    text = await page.inner_text("body")
                    results.append({"url": link, "content": text[:5000]})
                except:
                    pass
            
            await browser.close()
        return results

    def generate_report(self, query, research_data):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Report_{query.replace(' ', '_')}_{timestamp}.txt"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"DEEP-DIVE RESEARCH REPORT: {query}\n")
            f.write("="*50 + "\n\n")
            for i, data in enumerate(research_data):
                f.write(f"Source {i+1}: {data['url']}\n")
                f.write(f"Key Insights: {data['content'][:500]}...\n")
                f.write("-" * 30 + "\n")
        return filepath
