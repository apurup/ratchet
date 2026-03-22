"""
Model abstraction layer - supports MiniMax (Anthropic-format), Qwen, OpenAI, etc.
"""

import os
import json
import time
from typing import Optional
from dataclasses import dataclass
import httpx


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: dict
    cost: float
    latency_ms: float
    thinking: Optional[str] = None
    raw: Optional[dict] = None


class ModelClient:
    """Abstract base for model clients"""
    def complete(self, prompt: str, **kwargs) -> ModelResponse:
        raise NotImplementedError


class MiniMaxClient(ModelClient):
    """
    MiniMax API client using Anthropic Messages API format.
    
    Supports:
    - Standard chat completions via Anthropic-compatible endpoint
    - Thinking (reasoning) extraction
    - Token caching (cacheRead: $0.03/M, cacheWrite: $0.12/M vs input: $0.30/M)
    
    Endpoint: https://api.minimax.io/anthropic/v1/messages
    """
    def __init__(self, api_key: str = None, base_url: str = "https://api.minimax.io/anthropic"):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        self.base_url = base_url

    def complete(self, prompt: str, model: str = "MiniMax-M2.7", **kwargs) -> ModelResponse:
        start = time.time()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 8192),
        }
        
        # Optional: enable thinking if model supports it
        # MiniMax M2.7 has reasoning enabled by default
        
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
            )
        
        latency_ms = (time.time() - start) * 1000
        
        if response.status_code != 200:
            raise Exception(f"MiniMax API error: {response.status_code} {response.text[:300]}")
        
        data = response.json()
        
        # Parse content blocks - MiniMax returns an array of content blocks
        # Each block has type: "thinking" or "text"
        content_blocks = data.get("content", [])
        
        response_text = ""
        thinking_text = ""
        
        for block in content_blocks:
            if block.get("type") == "text":
                response_text += block.get("text", "")
            elif block.get("type") == "thinking":
                thinking_text += block.get("thinking", "")
        
        # Usage and cost calculation
        # MiniMax pricing (per 1M tokens):
        #   Input: $0.30 | Output: $1.20
        #   Cache Read: $0.03 (90% off!) | Cache Write: $0.12
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        
        # Check for cache hit (MiniMax may include this)
        cache_hit = usage.get("cache_hit", False)
        
        if cache_hit:
            cost = input_tokens * 0.03 / 1_000_000
        else:
            cost = (input_tokens * 0.3 + output_tokens * 1.2) / 1_000_000
        
        return ModelResponse(
            content=response_text.strip(),
            model=model,
            usage=usage,
            cost=cost,
            latency_ms=latency_ms,
            thinking=thinking_text.strip() if thinking_text else None,
            raw=data,
        )


class QwenClient(ModelClient):
    """Qwen API client (OpenAI-compatible)"""
    def __init__(self, api_key: str = None, base_url: str = "https://api.qwen.com/v1"):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        self.base_url = base_url

    def complete(self, prompt: str, model: str = "qwen3.5-32b", **kwargs) -> ModelResponse:
        start = time.time()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 8192),
        }
        if kwargs.get("temperature"):
            payload["temperature"] = kwargs["temperature"]

        with httpx.Client(timeout=120) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)

        latency_ms = (time.time() - start) * 1000

        if response.status_code != 200:
            raise Exception(f"Qwen API error: {response.status_code} {response.text[:200]}")

        data = response.json()
        return ModelResponse(
            content=data["choices"][0]["message"]["content"],
            model=model,
            usage=data.get("usage", {}),
            cost=0,
            latency_ms=latency_ms,
            raw=data,
        )


def get_client(provider: str = "minimax", **kwargs) -> ModelClient:
    clients = {"minimax": MiniMaxClient, "qwen": QwenClient}
    return clients.get(provider.lower(), MiniMaxClient)(**kwargs)
