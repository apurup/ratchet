#!/usr/bin/env python3
import asyncio
import json
import os
import sys
sys.path.insert(0, '/workspace/ratchet')

from ratchet.skills.research import ResearchSkill
from ratchet.models import MiniMaxClient
from ratchet.curator import Curator
from ratchet.mcp_client import PlaywrightMCPClient, MCPClient
import httpx

# ── Patch MCPClient for shell mode (fixes node pipe buffering) ──
_client_init_state = {}

async def _init_mcp_process(proc):
    init_req = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "ratchet", "version": "1.0"}},
    }
    proc.stdin.write((json.dumps(init_req) + "\n").encode())
    await proc.stdin.drain()
    resp = await proc.stdout.readline()
    return json.loads(resp.decode())

async def patched_call_stdio(self, tool_name, arguments):
    cid = id(self)
    if self._process is None or self._process.returncode is not None:
        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        _client_init_state[cid] = False
    
    if not _client_init_state.get(cid, False):
        await _init_mcp_process(self._process)
        _client_init_state[cid] = True

    request = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    request_json = json.dumps(request) + "\n"
    self._process.stdin.write(request_json.encode())
    await self._process.stdin.drain()
    response_line = await self._process.stdout.readline()
    response = json.loads(response_line.decode())
    if "error" in response:
        raise Exception(f"MCP tool error: {response['error']}")
    return response.get("result", {})

MCPClient._call_stdio = patched_call_stdio

# ── Override PlaywrightMCPClient methods to use browser_ prefix ──
from ratchet.mcp_client import PlaywrightMCPClient as OriginalPWC

async def new_navigate(self, url):
    return await self.call_tool("browser_navigate", {"url": url})
async def new_screenshot(self, name="screenshot.png"):
    return await self.call_tool("browser_screenshot", {"name": name})
async def new_click(self, selector):
    return await self.call_tool("browser_click", {"selector": selector})
async def new_type_text(self, selector, text):
    return await self.call_tool("browser_type", {"selector": selector, "text": text})
async def new_extract_content(self, selector):
    return await self.call_tool("browser_snapshot", {"selector": selector})
async def new_evaluate(self, script):
    # Try browser_evaluate with 'expression' param (may need to check schema)
    result = await self.call_tool("browser_evaluate", {"expression": script})
    return result

OriginalPWC.navigate = new_navigate
OriginalPWC.screenshot = new_screenshot
OriginalPWC.click = new_click
OriginalPWC.type_text = new_type_text
OriginalPWC.extract_content = new_extract_content
OriginalPWC.evaluate = new_evaluate

# ── Custom ResearchSkill that handles Google block + parse issues ──
class FixedResearchSkill(ResearchSkill):
    """ResearchSkill with fixes for common issues"""
    
    async def _search(self, query: str):
        """Search - use Bing to avoid Google CAPTCHA"""
        try:
            # Use DuckDuckGo instead of Google (less likely to block)
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            print(f"   Navigating to: {search_url[:60]}...")
            await self.mcp.navigate(search_url)
            await asyncio.sleep(4)
            
            await self.mcp.screenshot("search_results.png")
            
            # DuckDuckGo HTML structure
            script = """
            () => {
                const results = [];
                const items = document.querySelectorAll('article[data-result]');
                if (items.length === 0) {
                    // Try alternative selectors
                    const links = document.querySelectorAll('a[href^="http"]');
                    links.forEach((link, i) => {
                        if (i < 15 && link.textContent.trim()) {
                            const parent = link.parentElement;
                            results.push({
                                title: link.textContent.trim(),
                                url: link.href,
                                snippet: parent ? parent.textContent.trim().slice(0, 200) : ''
                            });
                        }
                    });
                } else {
                    items.forEach((item, i) => {
                        if (i < 10) {
                            const titleEl = item.querySelector('h2 a') || item.querySelector('a');
                            const snippetEl = item.querySelector('.snippet') || item.querySelector('.description');
                            if (titleEl) {
                                results.push({
                                    title: titleEl.textContent,
                                    url: titleEl.href,
                                    snippet: snippetEl ? snippetEl.textContent : ''
                                });
                            }
                        }
                    });
                }
                return JSON.stringify(results);
            }
            """
            
            result = await self.mcp.evaluate(script)
            
            if isinstance(result, dict) and "content" in result:
                for c in result["content"]:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text = c["text"]
                        if "### Result" in text:
                            start = text.find("### Result") + len("### Result")
                            json_str = text[start:].strip()
                            try:
                                parsed = json.loads(json_str)
                                return parsed
                            except:
                                return self._parse_js_result(text, "search")
            
            return []
            
        except Exception as e:
            print(f"   Search error: {e}")
            return []
    
    async def _browse_page(self, url: str):
        """Browse and extract content"""
        try:
            await self.mcp.navigate(url)
            await asyncio.sleep(3)
            
            await self.mcp.screenshot(f"page_{hash(url) % 1000}.png")
            
            # Extract main content
            script = """
            () => {
                const selectors = ['article', 'main', '.content', '#content', '.post-content', '.article-body', 'body'];
                let content = '';
                
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.textContent.length > 200) {
                        content = el.textContent.slice(0, 3000);
                        break;
                    }
                }
                
                if (!content) {
                    content = document.body.textContent.slice(0, 3000);
                }
                
                content = content.replace(/\\s+/g, ' ').trim();
                return content;
            }
            """
            
            result = await self.mcp.evaluate(script)
            
            if isinstance(result, dict) and "content" in result:
                for c in result["content"]:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text = c["text"]
                        if "### Result" in text:
                            return text.replace("### Result", "").strip()
            
            return ""
            
        except Exception as e:
            print(f"   Browse error for {url}: {e}")
            return ""

# ── Run the research test ──
async def main():
    print("="*60)
    print("RESEARCH SKILL TEST - Latest Information")
    print("="*60)

    topic = "Latest Python 3.13 features"

    print(f"\nTopic: {topic}")
    print("This tests how well Ratchet can fetch LATEST info from the web\n")

    mcp_cmd = "/usr/local/bin/npx --yes @playwright/mcp --no-sandbox --headless --executable-path=/usr/bin/chromium"
    mcp = PlaywrightMCPClient(command=mcp_cmd)
    
    # Use fixed skill with DuckDuckGo
    skill = FixedResearchSkill(mcp_client=mcp)
    model = MiniMaxClient()
    curator = Curator(storage_path="/workspace/ratchet/data/latest_info_test.json")

    try:
        lesson = await skill.execute(
            topic=topic,
            curator=curator,
            model=model,
            max_pages=3,
        )

        print(f"\n✅ Research complete!")
        print(f"\nKey Points Found:")
        for i, point in enumerate(lesson.key_points[:7], 1):
            print(f"  {i}. {point}")

        print(f"\nSources ({len(lesson.sources)}):")
        for s in lesson.sources[:5]:
            print(f"  - {s}")

        print(f"\nCurator stored: {len(curator.lessons)} lessons")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        skill.close()

asyncio.run(main())
