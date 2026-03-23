#!/usr/bin/env python3
"""Debug MCP client with proper env"""
import asyncio
import json
import os
import sys

sys.path.insert(0, '/workspace/ratchet')

import httpx
from ratchet.mcp_client import PlaywrightMCPClient, MCPClient

# Monkey-patch MCPClient to include proper env
original_call_stdio = MCPClient._call_stdio
original_list_tools = MCPClient.list_tools

async def patched_call_stdio(self, tool_name, arguments):
    if self._process is None or self._process.returncode is not None:
        cmd = self.command.split()
        env = os.environ.copy()
        env.update(self.env)
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        }
    }
    
    request_json = json.dumps(request) + "\n"
    self._process.stdin.write(request_json.encode())
    await self._process.stdin.drain()
    
    response_line = await self._process.stdout.readline()
    response = json.loads(response_line.decode())
    
    if "error" in response:
        raise Exception(f"MCP tool error: {response['error']}")
    
    return response.get("result", {})

async def patched_list_tools(self):
    if self.base_url:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/tools")
            return response.json().get("tools", [])
    else:
        cmd = self.command.split()
        env = os.environ.copy()
        env.update(self.env)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        proc.stdin.write((json.dumps(request) + "\n").encode())
        await proc.stdin.drain()
        response_line = await proc.stdout.readline()
        response = json.loads(response_line.decode())
        await proc.wait()
        return response.get("result", {}).get("tools", [])

MCPClient._call_stdio = patched_call_stdio
MCPClient.list_tools = patched_list_tools

async def test_mcp():
    print("Testing MCP connection with patched env...")
    client = PlaywrightMCPClient(command="/usr/local/bin/npx @playwright/mcp")
    try:
        result = await client.list_tools()
        print(f"Tools available: {len(result)}")
        for t in result[:5]:
            print(f"  - {t.get('name', t)}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

asyncio.run(test_mcp())
