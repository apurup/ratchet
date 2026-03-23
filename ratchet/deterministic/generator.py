"""
Hermes-compatible Generator — bridges Hermes's model layer to Ratchet's Generator interface.
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class GenerationResult:
    """Matches Ratchet's GenerationResult for compatibility."""
    content: str
    model: str
    cost: float
    latency_ms: float
    steps_used: List[str] = None
    error: Optional[str] = None


class HermesGenerator:
    """
    Generator that wraps Hermes's AIAgent model call interface.

    Compatible with Ratchet's Generator interface but uses Hermes's
    model_tools and agent infrastructure for the actual API calls.
    """

    def __init__(self, agent: "AIAgent"):
        self._agent = agent
        self.total_cost: float = 0.0

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 8192,
        temperature: float = 0.3,
        **kwargs,
    ) -> GenerationResult:
        """
        Generate a response using Hermes's model client.

        Uses Hermes's _make_api_call if available, otherwise falls back
        to calling through the agent's provider infrastructure.
        """
        start = time.time()
        model = model or self._agent.model

        try:
            # Use Hermes's internal API call mechanism
            response = self._agent._make_api_call(
                prompt=prompt,
                system=system,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            latency_ms = (time.time() - start) * 1000
            content = response.get("content", "")
            actual_cost = response.get("cost", 0.0)
            self.total_cost += actual_cost

            return GenerationResult(
                content=content,
                model=response.get("model", model),
                cost=actual_cost,
                latency_ms=latency_ms,
                steps_used=[],
                error=response.get("error"),
            )

        except Exception as e:
            return GenerationResult(
                content="",
                model=model,
                cost=0.0,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def extract_code(self, content: str, language: str = "python") -> Optional[str]:
        """
        Extract a code block from a markdown-formatted response.

        Matches Ratchet's extract_code logic.
        """
        import re

        # Try language-specific block first
        pattern = rf"```{language}[\s\S]*?```"
        match = re.search(pattern, content)
        if match:
            return match.group(0)[len(f"```{language}"):-3].strip()

        # Try any code block
        pattern = r"```[\s\S]*?```"
        match = re.search(pattern, content)
        if match:
            inner = match.group(0)[3:-3].strip()
            # Strip language tag if present
            if "\n" in inner:
                inner = inner.split("\n", 1)[1]
            return inner

        return content.strip()

    def generate_with_steps(
        self,
        prompt: str,
        steps: List["Step"],
        context: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """
        Generate using a multi-step skill definition.

        For each PROMPT step, render the prompt template with context and call generate().
        Concatenates outputs.
        """
        context = context or {}
        result = GenerationResult(content="", model=self._agent.model, cost=0.0, latency_ms=0.0)
        steps_used = []

        for step in steps:
            if step.type == "PROMPT":
                step_prompt = self._render_prompt(step.prompt or prompt, context)
                resp = self.generate(step_prompt)
                result.content = resp.content
                result.cost += resp.cost
                result.latency_ms += resp.latency_ms
                steps_used.append(step.id)
                if resp.error:
                    result.error = resp.error
                    break

        result.steps_used = steps_used
        return result

    def _render_prompt(self, template: str, context: Dict[str, Any]) -> str:
        """Simple {placeholder} template rendering."""
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered
