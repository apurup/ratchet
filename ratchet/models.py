"""
Model abstraction layer - supports MiniMax, Qwen, LM Studio (local), OpenAI-compatible APIs.
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
        content_blocks = data.get("content", [])
        
        response_text = ""
        thinking_text = ""
        
        for block in content_blocks:
            if block.get("type") == "text":
                response_text += block.get("text", "")
            elif block.get("type") == "thinking":
                thinking_text += block.get("thinking", "")
        
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        
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
        if kwargs.get("temperature") is not None:
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


class OpenAICompatibleClient(ModelClient):
    """
    Generic OpenAI-compatible API client.
    
    Works with:
    - LM Studio (local models via host.docker.internal)
    - Ollama
    - LocalAI
    - Any OpenAI-compatible API proxy
    
    Default base_url: http://host.docker.internal:1234/v1 (LM Studio on Mac)
    """
    def __init__(
        self,
        api_key: str = "dummy",
        base_url: str = "http://host.docker.internal:1234/v1",
        default_model: str = "local-model",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def complete(self, prompt: str, model: str = None, **kwargs) -> ModelResponse:
        start = time.time()
        
        model = model or self.default_model
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        
        # Optional parameters
        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        if kwargs.get("top_p") is not None:
            payload["top_p"] = kwargs["top_p"]
        if kwargs.get("stop") is not None:
            payload["stop"] = kwargs["stop"]

        with httpx.Client(timeout=300) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

        latency_ms = (time.time() - start) * 1000

        if response.status_code != 200:
            raise Exception(f"OpenAI-compatible API error: {response.status_code} {response.text[:300]}")

        data = response.json()
        
        # Parse response
        choices = data.get("choices", [])
        if choices and len(choices) > 0:
            content = choices[0].get("message", {}).get("content", "")
        else:
            content = ""

        return ModelResponse(
            content=content,
            model=model,
            usage=data.get("usage", {}),
            cost=0,  # Free for local models
            latency_ms=latency_ms,
            raw=data,
        )

    def list_models(self) -> list:
        """List available models from the API"""
        with httpx.Client(timeout=30) as client:
            response = client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
        
        if response.status_code != 200:
            raise Exception(f"Failed to list models: {response.status_code}")
        
        data = response.json()
        return [m.get("id") for m in data.get("data", [])]


def get_client(provider: str = "minimax", **kwargs) -> ModelClient:
    """
    Factory to get a model client by provider name.
    
    Providers:
    - "minimax" / "minimaxi" - MiniMax API (default)
    - "qwen" / "dashscope" - Qwen API
    - "lmstudio" / "local" / "lm" - LM Studio (local models)
    - "openai" - Generic OpenAI-compatible API
    """
    # Filter out None values so clients can use their defaults
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    provider = provider.lower()
    
    if provider in ("lmstudio", "local", "lm"):
        return OpenAICompatibleClient(**kwargs)
    elif provider == "openai":
        return OpenAICompatibleClient(**kwargs)
    elif provider in ("minimax", "minimaxi"):
        return MiniMaxClient(**kwargs)
    elif provider in ("qwen", "dashscope"):
        return QwenClient(**kwargs)
    else:
        # Default to MiniMax
        return MiniMaxClient(**kwargs)
