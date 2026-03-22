#!/usr/bin/env python3
import asyncio
import json
import os
import sys
sys.path.insert(0, '/workspace/ratchet')

from ratchet.mcp_client import PlaywrightMCPClient, MCPClient
import httpx

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

from ratchet.mcp_client import PlaywrightMCPClient as OriginalPWC

async def new_navigate(self, url):
    result = await self.call_tool("browser_navigate", {"url": url})
    print(f"  [DEBUG navigate] result: {str(result)[:400]}")
    return result

async def new_evaluate(self, script):
    result = await self.call_tool("browser_evaluate", {"script": script})
    print(f"  [DEBUG evaluate] type: {type(result)}, keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
    if isinstance(result, dict) and "content" in result:
        for c in result["content"]:
            print(f"  [DEBUG content]: {str(c)[:400]}")
    return result

OriginalPWC.navigate = new_navigate
OriginalPWC.evaluate = new_evaluate

async def main():
    mcp_cmd = "/usr/local/bin/npx --yes @playwright/mcp --no-sandbox --headless --executable-path=/usr/bin/chromium"
    client = PlaywrightMCPClient(command=mcp_cmd)
    
    print("Step 1: Navigate to Google search...")
    try:
        await client.navigate("https://www.google.com/search?q=Latest+Python+3.13+features")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nStep 2: Wait 4s for page load...")
    await asyncio.sleep(4)
    
    print("\nStep 3: Evaluate JS to extract results...")
    script = """() => {
        const results = [];
        const items = document.querySelectorAll('div.g');
        items.forEach((item, i) => {
            if (i < 10) {
                const titleEl = item.querySelector('h3');
                const linkEl = item.querySelector('a');
                if (titleEl && linkEl) {
                    results.push({ title: titleEl.textContent, url: linkEl.href });
                }
            }
        });
        return JSON.stringify(results);
    }"""
    try:
        result = await client.evaluate(script)
        print(f"  Final: {str(result)[:800]}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    client.close()

asyncio.run(main())
