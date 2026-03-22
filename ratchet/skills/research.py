"""
Research Skill - Ratchet learns from the web using browser automation.

Uses Playwright MCP to:
1. Search Google for a topic
2. Browse relevant pages
3. Extract key information
4. Store findings in curator

Usage:
    from ratchet.skills.research import ResearchSkill
    
    research_skill = ResearchSkill()
    result = await research_skill.execute(
        topic="Databricks Unity Catalog setup",
        curator=curator,
        model=client,
    )
"""

import asyncio
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from ratchet.mcp_client import PlaywrightMCPClient


@dataclass
class ResearchLesson:
    """A lesson learned from research"""
    topic: str
    summary: str
    key_points: List[str]
    sources: List[str]
    raw_notes: str


class ResearchSkill:
    """
    Browser-based research skill for Ratchet.
    
    Uses Playwright MCP to autonomously browse the web and learn.
    """
    
    def __init__(
        self,
        mcp_client: Optional[PlaywrightMCPClient] = None,
        headless: bool = True,
    ):
        self.mcp = mcp_client or PlaywrightMCPClient()
        self.headless = headless
    
    async def execute(
        self,
        topic: str,
        curator=None,
        model=None,
        max_pages: int = 3,
    ) -> ResearchLesson:
        """
        Research a topic using browser automation.
        
        Args:
            topic: What to research (e.g., "Databricks Unity Catalog setup")
            curator: Optional curator to store lessons
            model: Optional model to summarize findings
            max_pages: Maximum pages to browse
            
        Returns:
            ResearchLesson with findings
        """
        print(f"\n🔍 Researching: {topic}")
        
        # Step 1: Search for the topic
        search_results = await self._search(topic)
        print(f"   Found {len(search_results)} results")
        
        # Step 2: Browse top pages
        findings = []
        sources = []
        
        for i, result in enumerate(search_results[:max_pages], 1):
            print(f"   Browsing page {i}/{max_pages}: {result['title'][:50]}...")
            
            content = await self._browse_page(result["url"])
            if content:
                findings.append({
                    "title": result["title"],
                    "url": result["url"],
                    "content": content[:2000],  # Limit content per page
                })
                sources.append(result["url"])
        
        # Step 3: Extract key points
        key_points = await self._extract_key_points(findings, topic, model)
        
        # Step 4: Create summary
        summary = self._create_summary(topic, key_points, findings)
        
        # Step 5: Store in curator if provided
        if curator:
            from ratchet.curator import RepairLesson
            import uuid
            
            lesson = RepairLesson(
                id=str(uuid.uuid4()),
                failure_pattern=f"research_{topic.lower().replace(' ', '_')}",
                error_signature=topic,
                context=topic,
                repair_strategy=summary,
                fix_code=json.dumps(key_points),
                model_used="research-skill",
            )
            curator.add_lesson(lesson)
            print(f"   Stored lesson in curator")
        
        return ResearchLesson(
            topic=topic,
            summary=summary,
            key_points=key_points,
            sources=sources,
            raw_notes=json.dumps(findings, indent=2),
        )
    
    async def _search(self, query: str) -> List[Dict[str, str]]:
        """Search for a query using Playwright"""
        try:
            # Navigate to Google
            await self.mcp.navigate(f"https://www.google.com/search?q={query}")
            await asyncio.sleep(2)  # Wait for page to load
            
            # Take screenshot for debugging
            await self.mcp.screenshot("search_results.png")
            
            # Extract search results using evaluate
            script = """
            () => {
                const results = [];
                const items = document.querySelectorAll('div.g');
                items.forEach((item, i) => {
                    if (i < 10) {
                        const titleEl = item.querySelector('h3');
                        const linkEl = item.querySelector('a');
                        const snippetEl = item.querySelector('div[data-sncf]');
                        if (titleEl && linkEl) {
                            results.push({
                                title: titleEl.textContent,
                                url: linkEl.href,
                                snippet: snippetEl ? snippetEl.textContent : ''
                            });
                        }
                    }
                });
                return results;
            }
            """
            result = await self.mcp.evaluate(script)
            
            # Parse result
            if isinstance(result, dict) and "result" in result:
                text = result["result"]
                # Extract from the output
                return self._parse_js_result(text, "search")
            return []
            
        except Exception as e:
            print(f"   Search error: {e}")
            return []
    
    async def _browse_page(self, url: str) -> str:
        """Browse a page and extract content"""
        try:
            await self.mcp.navigate(url)
            await asyncio.sleep(3)  # Wait for page to load
            
            await self.mcp.screenshot(f"page_{url.split('/')[-1][:20]}.png")
            
            # Extract main content
            script = """
            () => {
                // Try to find main content
                const selectors = ['article', 'main', '.content', '#content', '.post-content', '.article-body'];
                let content = '';
                
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        content = el.textContent.slice(0, 3000);
                        break;
                    }
                }
                
                if (!content) {
                    // Fallback to body
                    content = document.body.textContent.slice(0, 3000);
                }
                
                // Clean up whitespace
                content = content.replace(/\\s+/g, ' ').trim();
                return content;
            }
            """
            
            result = await self.mcp.evaluate(script)
            
            if isinstance(result, dict) and "result" in result:
                return result["result"]
            elif isinstance(result, str):
                return result
            return ""
            
        except Exception as e:
            print(f"   Browse error for {url}: {e}")
            return ""
    
    async def _extract_key_points(
        self,
        findings: List[Dict],
        topic: str,
        model=None,
    ) -> List[str]:
        """Extract key points from findings using AI"""
        if not findings or not model:
            return []
        
        # Combine findings
        combined = "\n\n".join([
            f"## {f['title']}\n{f['content'][:1000]}"
            for f in findings
        ])
        
        prompt = f"""Extract 5-7 key points from these research findings about "{topic}".

Findings:
{combined}

Return a JSON array of strings, each string is one key point. Be specific and concise.
Example: ["Point 1 about...", "Point 2 about...", ...]

JSON:"""
        
        try:
            response = model.complete(prompt, max_tokens=1000)
            text = response.content
            
            # Try to parse JSON
            if "[" in text:
                start = text.find("[")
                end = text.find("]") + 1
                json_str = text[start:end]
                points = json.loads(json_str)
                if isinstance(points, list):
                    return [str(p) for p in points]
        except:
            pass
        
        return [f["content"][:200] for f in findings[:5]]
    
    def _create_summary(
        self,
        topic: str,
        key_points: List[str],
        findings: List[Dict],
    ) -> str:
        """Create a summary of the research"""
        lines = [
            f"## Research: {topic}",
            "",
            "### Key Points:",
        ]
        
        for i, point in enumerate(key_points, 1):
            lines.append(f"{i}. {point}")
        
        lines.extend([
            "",
            "### Sources:",
        ])
        
        for finding in findings:
            lines.append(f"- {finding['title']}: {finding['url']}")
        
        return "\n".join(lines)
    
    def _parse_js_result(self, text: str, result_type: str) -> List[Dict]:
        """Parse JavaScript evaluation result"""
        try:
            # Try to extract JSON from the result
            if "result" in text:
                start = text.find('"result"')
                if start != -1:
                    brace_start = text.find('[', start)
                    brace_end = text.rfind(']') + 1
                    if brace_start != -1 and brace_end != -1:
                        json_str = text[brace_start:brace_end]
                        return json.loads(json_str)
        except:
            pass
        return []
    
    def close(self):
        """Clean up resources"""
        self.mcp.close()
    
    def __del__(self):
        self.close()


# Standalone research function for quick use
async def research(
    topic: str,
    curator=None,
    model=None,
    max_pages: int = 3,
) -> ResearchLesson:
    """
    Quick research function.
    
    Usage:
        lesson = await research(
            topic="Databricks Unity Catalog setup",
            curator=my_curator,
            model=my_model,
        )
    """
    skill = ResearchSkill()
    try:
        return await skill.execute(
            topic=topic,
            curator=curator,
            model=model,
            max_pages=max_pages,
        )
    finally:
        skill.close()


if __name__ == "__main__":
    # Test
    async def test():
        skill = ResearchSkill()
        lesson = await skill.execute("Python list comprehension")
        print(f"\nSummary:\n{lesson.summary}")
        print(f"\nKey points: {lesson.key_points}")
        skill.close()
    
    asyncio.run(test())
