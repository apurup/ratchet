"""
Model abstraction layer - supports MiniMax, Qwen, OpenAI, etc.
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
    raw: Optional[dict] = None


class ModelClient:
    """Abstract base for model clients"""
    def complete(self, prompt: str, **kwargs) -> ModelResponse:
        raise NotImplementedError


class MiniMaxClient(ModelClient):
    """MiniMax API client - uses MiniMax Chat Completions API"""
    def __init__(self, api_key: str = None, base_url: str = "https://api.minimax.io/v1"):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        self.base_url = base_url

    def complete(self, prompt: str, model: str = "MiniMax-M2.7", **kwargs) -> ModelResponse:
        start = time.time()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 8192),
        }

        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.base_url}/text/chatcompletion_v2",
                headers=headers,
                json=payload,
            )

        latency_ms = (time.time() - start) * 1000

        if response.status_code != 200:
            raise Exception(f"MiniMax API error: {response.status_code} {response.text[:200]}")

        data = response.json()

        # Extract content from MiniMax response format
        choices = data.get("choices", [])
        if choices and len(choices) > 0:
            content = choices[0].get("messages", [{}])[0].get("text", "")
        else:
            content = ""

        # Usage: MiniMax charges per 1M tokens
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = (input_tokens * 0.3 + output_tokens * 1.2) / 1_000_000

        return ModelResponse(
            content=content,
            model=model,
            usage=usage,
            cost=cost,
            latency_ms=latency_ms,
            raw=data,
        )


class QwenClient(ModelClient):
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
