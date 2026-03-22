"""
Generator - Model interaction and code generation layer
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ratchet.models import ModelResponse, get_client, ModelClient
from ratchet.skill import Step, StepType


@dataclass
class GenerationResult:
    content: str
    model: str
    cost: float
    latency_ms: float
    steps_used: List[str] = field(default_factory=list)
    error: Optional[str] = None


class Generator:
    """Handles model interaction and code generation."""

    def __init__(
        self,
        client: Optional[ModelClient] = None,
        model: str = "MiniMax-M2.7",
        max_tokens: int = 8192,
        provider: str = "minimax",
    ):
        self.client = client or get_client(provider=provider)
        self.model = model
        self.max_tokens = max_tokens
        self.provider = provider

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> GenerationResult:
        """Generate a response from the model."""
        start = time.time()

        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        try:
            response = self.client.complete(
                prompt=full_prompt,
                model=kwargs.get("model", self.model),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )

            latency_ms = (time.time() - start) * 1000

            return GenerationResult(
                content=response.content,
                model=response.model,
                cost=response.cost,
                latency_ms=latency_ms,
            )
        except Exception as e:
            return GenerationResult(
                content="",
                model=self.model,
                cost=0.0,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def generate_with_steps(
        self,
        prompt: str,
        steps: List[Step],
        context: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """Generate using a multi-step skill definition."""
        context = context or {}
        result = GenerationResult(content="", model=self.model, cost=0.0, latency_ms=0.0)

        for step in steps:
            if step.type == StepType.PROMPT:
                step_prompt = self._render_prompt(step.prompt, context)
                resp = self.generate(step_prompt)
                result.content = resp.content
                result.cost += resp.cost
                result.latency_ms += resp.latency_ms
                result.steps_used.append(step.id)
                if resp.error:
                    result.error = resp.error
                    break
            elif step.type == StepType.BRANCH:
                # Branch handled by agent loop
                pass

        return result

    def _render_prompt(self, template: str, context: Dict[str, Any]) -> str:
        """Simple template rendering for prompts."""
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered

    def extract_code(self, content: str, language: str = "python") -> Optional[str]:
        """Extract code block from markdown-formatted response."""
        if f"```{language}" in content:
            start = content.find(f"```{language}") + len(f"```{language}")
            end = content.find("```", start)
            return content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            return content[start:end].strip()
        return content.strip()
