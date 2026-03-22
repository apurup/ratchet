#!/usr/bin/env python3
import asyncio
import json
import os
import sys
sys.path.insert(0, '/workspace/ratchet')

from ratchet.mcp_client import PlaywrightMCPClient, MCPClient

_client_init_state = {}

async def _init_mcp_process(proc):
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "ratchet", "version": "1.0"}}}
    proc.stdin.write((json.dumps(init_req) + "\n").encode())
    await proc.stdin.drain()
    return json.loads((await proc.stdout.readline()).decode())

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
    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": tool_name, "arguments": arguments}}
    self._process.stdin.write((json.dumps(request) + "\n").encode())
    await self._process.stdin.drain()
    response = json.loads((await self._process.stdout.readline()).decode())
    if "error" in response:
        raise Exception(f"MCP error: {response['error']}")
    return response.get("result", {})

MCPClient._call_stdio = patched_call_stdio

from ratchet.mcp_client import PlaywrightMCPClient as Orig

async def nav(self, url):
    return await self.call_tool("browser_navigate", {"url": url})
async def ev(self, script):
    # Try CDP-based evaluate
    return await self.call_tool("browser_evaluate_cdp", {"expression": script})
async def snap(self):
    return await self.call_tool("browser_snapshot", {})

Orig.navigate = nav
Orig.evaluate = ev
Orig.extract_content = snap

async def main():
    client = PlaywrightMCPClient(command="/usr/local/bin/npx --yes @playwright/mcp --no-sandbox --headless --executable-path=/usr/bin/chromium")
    
    print("1. Navigate to DuckDuckGo...")
    await client.navigate("https://duckduckgo.com/?q=Latest+Python+3.13+features")
    print("   OK")
    
    await asyncio.sleep(4)
    
    print("\n2. Try browser_evaluate_cdp...")
    try:
        r = await client.evaluate("() => document.title")
        print(f"   cdp result: {str(r)[:400]}")
    except Exception as e:
        print(f"   Error: {e}")
    
    await asyncio.sleep(1)
    
    print("\n3. Try browser_snapshot for full content...")
    try:
        r = await client.extract_content()
        print(f"   snapshot: {str(r)[:800]}")
    except Exception as e:
        print(f"   Error: {e}")
    
    client.close()

asyncio.run(main())
