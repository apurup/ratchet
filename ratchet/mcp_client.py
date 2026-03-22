"""
MCP Client - Connect Ratchet to MCP servers (Playwright, Brave Search, Filesystem, etc.)
"""

import json
import subprocess
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import httpx


class MCPClient:
    """
    MCP client that connects to MCP servers via stdio (npx/node) or HTTP.
    
    Supports:
    - stdio-based servers (npx @playwright/mcp-server)
    - HTTP-based MCP servers
    
    Usage:
        client = MCPClient("playwright")
        result = await client.call_tool("browser_navigate", {"url": "https://..."})
    """
    
    def __init__(
        self,
        server: str = "playwright",
        command: Optional[str] = None,
        base_url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self.server = server
        self.command = command or self._default_command(server)
        self.base_url = base_url
        self.env = env or {}
        self._process = None
        
    def _default_command(self, server: str) -> str:
        commands = {
            "playwright": "npx @playwright/mcp",
            "brave-search": "npx @modelcontextprotocol/server-brave-search",
            "filesystem": "npx @modelcontextprotocol/server-filesystem",
            "git": "npx @modelcontextprotocol/server-git",
        }
        return commands.get(server, f"npx {server}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool by name with arguments.
        
        Uses HTTP API if base_url is set, otherwise uses stdio.
        """
        if self.base_url:
            return await self._call_http(tool_name, arguments)
        else:
            return await self._call_stdio(tool_name, arguments)
    
    async def _call_http(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call via HTTP (for servers that expose MCP over HTTP)"""
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/tools/{tool_name}",
                json=arguments,
            )
            response.raise_for_status()
            return response.json()
    
    async def _call_stdio(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call via stdio using the MCP JSON-RPC protocol.
        
        This spawns the server process and communicates via stdin/stdout.
        """
        import asyncio
        
        if self._process is None or self._process.returncode is not None:
            cmd = self.command.split()
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**self.env},
            )
        
        # MCP JSON-RPC request
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
        
        # Read response
        response_line = await self._process.stdout.readline()
        response = json.loads(response_line.decode())
        
        if "error" in response:
            raise Exception(f"MCP tool error: {response['error']}")
        
        return response.get("result", {})
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from the MCP server"""
        if self.base_url:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{self.base_url}/tools")
                return response.json().get("tools", [])
        else:
            # Use stdio to list tools
            import asyncio
            cmd = self.command.split()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Send list tools request
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
    
    def close(self):
        """Close the MCP server process"""
        if self._process and self._process.returncode is None:
            self._process.terminate()
    
    def __del__(self):
        self.close()


class PlaywrightMCPClient(MCPClient):
    """
    Specialized MCP client for Playwright browser automation.
    
    Provides a clean interface for browser operations like:
    - navigate
    - screenshot
    - click
    - type
    - evaluate
    - extract_content
    """
    
    def __init__(self, command: str = "npx @playwright/mcp"):
        super().__init__(server="playwright", command=command)
    
    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL"""
        return await self.call_tool("navigate", {"url": url})
    
    async def screenshot(self, name: str = "screenshot.png") -> Dict[str, Any]:
        """Take a screenshot"""
        return await self.call_tool("screenshot", {"name": name})
    
    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element"""
        return await self.call_tool("click", {"selector": selector})
    
    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into an element"""
        return await self.call_tool("type", {"selector": selector, "text": text})
    
    async def extract_content(self, selector: str) -> Dict[str, Any]:
        """Extract text content from an element"""
        return await self.call_tool("extract_content", {"selector": selector})
    
    async def evaluate(self, script: str) -> Dict[str, Any]:
        """Run JavaScript in the page context"""
        return await self.call_tool("evaluate", {"script": script})


def get_mcp_client(server: str = "playwright", **kwargs) -> MCPClient:
    """
    Factory to get an MCP client by server name.
    
    Servers:
    - "playwright" - Browser automation
    - "brave-search" - Web search
    - "filesystem" - File operations
    - "git" - Git operations
    """
    clients = {
        "playwright": PlaywrightMCPClient,
        "browser": PlaywrightMCPClient,
    }
    
    client_class = clients.get(server.lower(), MCPClient)
    return client_class(**kwargs)
