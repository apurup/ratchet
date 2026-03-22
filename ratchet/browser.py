"""
Direct Browser Tool - Uses Playwright directly (no MCP overhead)

Usage:
    browser = BrowserTool()
    await browser.search_wikipedia("Python 3.13 features")
    results = await browser.browse_page(url)
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class BrowserTool:
    """
    Direct Playwright browser automation + Wikipedia search.

    Features:
    - Navigate to URLs (any site)
    - Wikipedia search (reliable, no API key needed)
    - Get page content
    - Screenshot
    - Click/interact

    Note: Google/Bing/DuckDuckGo block headless browsers from data centers.
          Wikipedia search works reliably.
    """

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "playwright not installed. Run: pip install playwright && python -m playwright install chromium"
            )

        self.headless = headless
        self.browser_type = browser_type
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    async def _ensure_browser(self):
        """Lazily start browser"""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page()

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL"""
        await self._ensure_browser()
        response = await self._page.goto(url, wait_until="networkidle", timeout=30000)
        return {
            "url": self._page.url,
            "status": response.status if response else None,
            "title": await self._page.title(),
        }

    async def search_wikipedia(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search Wikipedia using their full-text search API (reliable, no API key needed).
        """
        import urllib.parse

        encoded_query = urllib.parse.quote(query)
        api_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json&srlimit={limit}"

        import httpx
        headers = {'User-Agent': 'Ratchet/0.2.0 (research agent; mailto:research@ratchet.ai)'}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(api_url, headers=headers)
            data = response.json()

        results_data = data.get('query', {}).get('search', [])
        
        results = []
        for r in results_data:
            # Clean HTML tags from snippet
            snippet = r.get('snippet', '')
            import re
            snippet = re.sub(r'<[^>]+>', '', snippet)
            
            results.append(SearchResult(
                title=r.get('title', ''),
                url=f"https://en.wikipedia.org/wiki/{urllib.parse.quote(r.get('title', '').replace(' ', '_'))}",
                snippet=snippet[:200],
            ))

        return {
            "query": query,
            "engine": "wikipedia",
            "results": results,
        }

    async def search(self, query: str) -> Dict[str, Any]:
        """Search using Wikipedia (default)"""
        return await self.search_wikipedia(query)

    async def get_page_content(
        self,
        selector: Optional[str] = None,
        max_length: int = 5000,
    ) -> str:
        """Get text content from the current page"""
        await self._ensure_browser()

        if selector:
            el = await self._page.query_selector(selector)
            if el:
                content = await el.inner_text()
            else:
                content = ""
        else:
            # Try multiple selectors for main content
            for sel in [
                '.mw-parser-output',  # Wikipedia
                'article',          # General
                '[role="main"]',    # ARIA main
                '#main-content',     # Wikipedia-style
                'main',              # HTML5 main
            ]:
                el = await self._page.query_selector(sel)
                if el:
                    content = await el.inner_text()
                    # Skip if too short (probably sidebar)
                    if len(content) > 500:
                        break
            else:
                content = await self._page.inner_text('body')

        return content[:max_length].strip()

    async def browse_page(self, url: str, max_length: int = 3000) -> Dict[str, Any]:
        """Navigate to a page and extract content"""
        await self.navigate(url)
        await asyncio.sleep(2)

        content = await self.get_page_content(max_length=max_length)

        return {
            "url": url,
            "title": await self._page.title(),
            "content": content,
        }

    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element"""
        await self._ensure_browser()
        await self._page.click(selector, timeout=10000)
        await asyncio.sleep(1)
        return {"success": True, "url": self._page.url}

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type into an input"""
        await self._ensure_browser()
        await self._page.fill(selector, text)
        return {"success": True}

    async def screenshot(self, path: str = "screenshot.png") -> Dict[str, Any]:
        """Take a screenshot"""
        await self._ensure_browser()
        await self._page.screenshot(path=path, full_page=True)
        return {"path": path}

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript in page context"""
        await self._ensure_browser()
        return await self._page.evaluate(script)

    async def close(self):
        """Close browser"""
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def __del__(self):
        try:
            if self._browser:
                self._browser.close()
        except:
            pass


async def research(
    topic: str,
    max_pages: int = 3,
    browser: Optional[BrowserTool] = None,
) -> Dict[str, Any]:
    """
    Quick research function - search Wikipedia, browse pages, extract.

    Usage:
        result = await research("Databricks Unity Catalog")
        for finding in result["findings"]:
            print(finding["title"], finding["content"][:200])
    """
    close_browser = browser is None
    browser = browser or BrowserTool()

    try:
        # Step 1: Search Wikipedia
        search_result = await browser.search(topic)
        results = search_result["results"]

        # Step 2: Browse top pages
        findings = []
        for i, r in enumerate(results[:max_pages]):
            try:
                page_data = await browser.browse_page(r.url)
                findings.append({
                    "title": page_data["title"],
                    "url": page_data["url"],
                    "snippet": r.snippet,
                    "content": page_data["content"][:2000],
                })
            except Exception as e:
                continue

        return {
            "topic": topic,
            "search_engine": search_result.get("engine", "wikipedia"),
            "search_results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results
            ],
            "findings": findings,
            "sources": [f["url"] for f in findings],
        }

    finally:
        if close_browser:
            await browser.close()


if __name__ == "__main__":
    async def test():
        print("Testing BrowserTool with Wikipedia search...")
        browser = BrowserTool()

        result = await browser.search_wikipedia("Python 3.13 features")
        print(f"\nWikipedia search found {len(result['results'])} results:")
        for r in result["results"][:3]:
            print(f"  - {r.title}")
            print(f"    {r.snippet[:80]}...")

        if result["results"]:
            page = await browser.browse_page(result["results"][0].url)
            print(f"\nBrowsed: {page['title']}")
            print(f"Content: {page['content'][:200]}...")

        await browser.close()
        print("\n✅ BrowserTool test complete!")

    asyncio.run(test())
