"""
MCP Client - Connect Ratchet to MCP servers

Supports:
- MiniMax Token Plan MCP (web_search, understand_image)
- Any stdio-based MCP server
"""

import json
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class MCPResponse:
    content: Any
    success: bool
    error: Optional[str] = None


class MCPClient:
    """
    MCP client for Ratchet.
    
    Connects to MCP servers via stdio (npx/uvx).
    
    Supports MiniMax Token Plan MCP:
    - web_search: Search the web
    - understand_image: Analyze images
    
    Usage:
        client = MCPClient()
        result = await client.call("web_search", {"query": "Databricks docs"})
        result = await client.call("understand_image", {"prompt": "What is this?", "image_url": "https://..."})
    """
    
    def __init__(
        self,
        command: str = "uvx",
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None,
        api_host: str = "https://api.minimax.io",
    ):
        self.command = command
        self.args = args or ["minimax-coding-plan-mcp", "-y"]
        self.api_key = api_key
        self.api_host = api_host
        self.env = env or {}
        self._initialized = False
        self._proc = None

        if api_key:
            self.env["MINIMAX_API_KEY"] = api_key
            self.env["MINIMAX_API_HOST"] = api_host

    async def _ensure_init(self) -> bool:
        """Perform MCP initialization handshake if not already done."""
        if self._initialized:
            return True

        import os
        import sys

        cmd = [self.command] + self.args
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.env},
        )

        # Step 1: send initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "clientInfo": {
                    "name": "ratchet-mcp-client",
                    "version": "1.0.0",
                },
            },
        }
        req_json = json.dumps(init_request) + "\n"
        self._proc.stdin.write(req_json.encode())
        await self._proc.stdin.drain()

        # Step 2: read server response
        resp_line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=60)
        resp = json.loads(resp_line.decode())
        if "error" in resp:
            await self._cleanup()
            return False

        # Step 3: send notifications/initialized
        notify = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n"
        self._proc.stdin.write(notify.encode())
        await self._proc.stdin.drain()

        self._initialized = True
        return True

    async def _cleanup(self):
        """Terminate the MCP subprocess."""
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                pass
            self._proc = None
            self._initialized = False

    async def call(self, tool: str, arguments: Dict[str, Any]) -> MCPResponse:
        """
        Call an MCP tool.

        Args:
            tool: Name of the tool (e.g., "web_search")
            arguments: Tool arguments (e.g., {"query": "..."})
        """
        try:
            # Ensure MCP session is initialized
            if not await self._ensure_init():
                return MCPResponse(content=None, success=False, error="MCP initialization failed")

            # JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool,
                    "arguments": arguments,
                }
            }

            request_json = json.dumps(request) + "\n"
            self._proc.stdin.write(request_json.encode())
            await self._proc.stdin.drain()

            # Read response
            response_line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=120)
            response = json.loads(response_line.decode())

            if "error" in response:
                return MCPResponse(
                    content=None,
                    success=False,
                    error=response["error"].get("message", str(response["error"])),
                )

            result = response.get("result", {})
            return MCPResponse(
                content=result.get("content", []),
                success=True,
            )

        except asyncio.TimeoutError:
            await self._cleanup()
            return MCPResponse(content=None, success=False, error="Timeout")
        except Exception as e:
            await self._cleanup()
            return MCPResponse(content=None, success=False, error=str(e))

    async def web_search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Search the web using MiniMax Token Plan MCP.
        
        Args:
            query: Search query
            num_results: Number of results to return
            
        Returns:
            Dict with search results and suggestions
        """
        result = await self.call("web_search", {"query": query})
        
        if not result.success:
            return {"error": result.error, "results": [], "suggestions": []}
        
        # Parse the response content
        content = result.content if isinstance(result.content, list) else []
        
        results = []
        suggestions = []
        
        for item in content:
            if isinstance(item, dict):
                text = item.get("text", "")
                # Parse the structured response
                if "results" in text.lower():
                    # Extract results from text
                    pass
                elif "suggestions" in text.lower():
                    pass
                else:
                    # Plain text result
                    if text.strip():
                        results.append(text.strip())
        
        return {
            "query": query,
            "results": results[:num_results],
            "suggestions": suggestions,
            "raw": content,
        }
    
    async def understand_image(
        self,
        image_url: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """
        Analyze an image using MiniMax Token Plan MCP.
        
        Args:
            image_url: URL or local path to image
            prompt: Question or analysis request
            
        Returns:
            Dict with analysis result
        """
        result = await self.call("understand_image", {
            "prompt": prompt,
            "image_url": image_url,
        })
        
        if not result.success:
            return {"error": result.error, "analysis": None}
        
        content = result.content if isinstance(result.content, list) else []
        
        # Extract text from content blocks
        analysis = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                analysis += item.get("text", "")
        
        return {
            "image_url": image_url,
            "prompt": prompt,
            "analysis": analysis.strip(),
            "raw": content,
        }


def get_mcp_client(
    server: str = "minimax",
    api_key: Optional[str] = None,
    **kwargs,
) -> MCPClient:
    """
    Factory to get MCP client.
    
    Args:
        server: Server name ("minimax" for MiniMax Token Plan MCP)
        api_key: API key (from MINIMAX_API_KEY env var if not provided)
        **kwargs: Additional arguments
    """
    import os
    
    api_key = api_key or os.environ.get("MINIMAX_API_KEY")
    api_host = kwargs.get("api_host", "https://api.minimax.io")
    
    if server.lower() == "minimax":
        return MCPClient(
            command="uvx",
            args=["minimax-coding-plan-mcp", "-y"],
            api_key=api_key,
            api_host=api_host,
        )
    
    # Default to MiniMax
    return MCPClient(api_key=api_key, api_host=api_host)
