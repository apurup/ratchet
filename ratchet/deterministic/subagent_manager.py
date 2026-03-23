"""
Verified Subagent Manager for Ratchet.

Spawns isolated subagents with deterministic execution and
verified result aggregation.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from typing import List, Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


# Maximum depth for subagent nesting (parent=0 -> child=1 -> grandchild rejected=2)
MAX_SUBAGENT_DEPTH = 2

# Tools that subagents must never have access to
BLOCKED_TOOLS = frozenset([
    "delegate_task",   # no recursive delegation
    "clarify",         # no user interaction
    "memory",          # no writes to shared MEMORY.md
    "send_message",    # no cross-platform side effects
    "execute_code",    # children should reason step-by-step, not write scripts
])

# Default toolsets for subagents
DEFAULT_TOOLSETS = ["terminal", "file", "web"]


def compute_subagent_seed(parent_seed: Optional[int], task_id: str, goal: str) -> int:
    """
    Derive a deterministic seed for a subagent from parent seed + task context.

    This ensures that the same subagent task always produces the same output
    when deterministic=True.
    """
    raw = f"{parent_seed or ''}:{task_id}:{goal}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:16], 16) % (2**63)


def _strip_blocked_tools(toolsets: List[str]) -> List[str]:
    """Remove toolsets that contain only blocked tools."""
    blocked_toolset_names = {"delegation", "clarify", "memory", "code_execution"}
    return [t for t in toolsets if t not in blocked_toolset_names]


class SubagentResult:
    """
    Result from a verified subagent execution.

    Attributes:
        task_id: Unique identifier for this subagent task.
        success: Whether the subagent completed successfully.
        output: The subagent's final output/summary.
        error: Error message if success=False.
        duration_ms: Execution time in milliseconds.
        trace_id: Optional execution trace ID for deterministic replay.
    """

    def __init__(
        self,
        task_id: str,
        success: bool,
        output: Any = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        trace_id: Optional[str] = None,
    ):
        self.task_id = task_id
        self.success = success
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.trace_id = trace_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "trace_id": self.trace_id,
        }


class SubagentManager:
    """
    Manages spawning of verified subagents with deterministic execution.

    Key features:
    - Each subagent runs with its own deterministic seed (derived from parent task + subagent_id)
    - Results are captured in SubagentResult with optional trace_id for replay
    - Parent can replay a subagent's work by calling replay_from_trace
    - Subagent isolation: env vars, iteration budget, tool restrictions enforced

    This builds on the existing delegate_task infrastructure but adds:
    - Deterministic seeding per subagent
    - Structured SubagentResult with trace IDs
    - Async spawn/wait API for cleaner integration
    - Integration with the deterministic replay system
    """

    def __init__(self, parent_agent: "AIAgent"):
        """
        Initialize the SubagentManager.

        Args:
            parent_agent: The parent AIAgent that owns this manager.
                         Subagents inherit credentials and configuration from it.
        """
        self.parent = parent_agent
        self.active_subagents: Dict[str, "AIAgent"] = {}
        self._results: Dict[str, SubagentResult] = {}
        self._parent_seed = getattr(parent_agent, "_deterministic_seed", None)
        self._lock = asyncio.Lock()

    def _build_child_system_prompt(self, goal: str, context: Optional[str] = None) -> str:
        """Build a focused system prompt for a child agent."""
        parts = [
            "You are a focused subagent working on a specific delegated task.",
            "",
            f"YOUR TASK:\n{goal}",
        ]
        if context and context.strip():
            parts.append(f"\nCONTEXT:\n{context}")
        parts.append(
            "\nComplete this task using the tools available to you. "
            "When finished, provide a clear, concise summary of:\n"
            "- What you did\n"
            "- What you found or accomplished\n"
            "- Any files you created or modified\n"
            "- Any issues encountered\n\n"
            "Be thorough but concise -- your response is returned to the "
            "parent agent as a summary."
        )
        return "\n".join(parts)

    def _build_child_agent(
        self,
        task_id: str,
        goal: str,
        context: Optional[Dict[str, Any]],
        max_iterations: int,
        toolsets: Optional[List[str]],
        deterministic: bool,
    ) -> "AIAgent":
        """
        Build a child AIAgent with isolated context.

        Args:
            task_id: Unique task identifier for this subagent.
            goal: The goal/task description.
            context: Additional context dict (passed as string to child).
            max_iterations: Max tool-calling turns for the child.
            toolsets: Toolsets to enable for the child.
            deterministic: Whether to use deterministic seeding.

        Returns:
            A configured AIAgent ready to run.
        """
        from run_agent import AIAgent

        # Determine effective toolsets (strip blocked ones)
        if toolsets:
            child_toolsets = _strip_blocked_tools(toolsets)
        elif getattr(self.parent, "enabled_toolsets", None):
            child_toolsets = _strip_blocked_tools(self.parent.enabled_toolsets)
        else:
            child_toolsets = _strip_blocked_tools(DEFAULT_TOOLSETS)

        # Build system prompt from goal + context
        context_str = None
        if context:
            context_str = json.dumps(context, indent=2) if isinstance(context, dict) else str(context)

        child_prompt = self._build_child_system_prompt(goal, context_str)

        # Compute deterministic seed if enabled
        effective_seed = None
        if deterministic:
            effective_seed = compute_subagent_seed(self._parent_seed, task_id, goal)

        # Inherit credentials from parent
        parent_api_key = getattr(self.parent, "api_key", None)
        if not parent_api_key and hasattr(self.parent, "_client_kwargs"):
            parent_api_key = self.parent._client_kwargs.get("api_key")

        # Resolve delegation depth
        parent_depth = getattr(self.parent, "_delegate_depth", 0)
        child_depth = parent_depth + 1

        child = AIAgent(
            base_url=self.parent.base_url,
            api_key=parent_api_key,
            model=self.parent.model,
            provider=getattr(self.parent, "provider", None),
            api_mode=getattr(self.parent, "api_mode", None),
            acp_command=getattr(self.parent, "acp_command", None),
            acp_args=list(getattr(self.parent, "acp_args", []) or []),
            max_iterations=max_iterations,
            max_tokens=getattr(self.parent, "max_tokens", None),
            reasoning_config=getattr(self.parent, "reasoning_config", None),
            prefill_messages=getattr(self.parent, "prefill_messages", None),
            enabled_toolsets=child_toolsets,
            quiet_mode=True,
            ephemeral_system_prompt=child_prompt,
            log_prefix=f"[subagent-{task_id[:8]}]",
            platform=self.parent.platform,
            skip_context_files=True,
            skip_memory=True,
            clarify_callback=None,
            session_db=getattr(self.parent, "_session_db", None),
            providers_allowed=getattr(self.parent, "providers_allowed", None),
            providers_ignored=getattr(self.parent, "providers_ignored", None),
            providers_order=getattr(self.parent, "providers_order", None),
            provider_sort=getattr(self.parent, "provider_sort", None),
            tool_progress_callback=None,
            iteration_budget=getattr(self.parent, "iteration_budget", None),
            deterministic_seed=effective_seed,
        )

        # Set delegation depth so children can't spawn grandchildren
        child._delegate_depth = child_depth

        # Track this child for interrupt propagation
        if hasattr(self.parent, "_active_children"):
            lock = getattr(self.parent, "_active_children_lock", None)
            if lock:
                with lock:
                    self.parent._active_children.append(child)
            else:
                self.parent._active_children.append(child)

        return child

    def spawn(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        max_iterations: int = 20,
        toolsets: Optional[List[str]] = None,
        deterministic: bool = True,
    ) -> str:
        """
        Spawn a subagent to work on a goal (synchronous version).

        This starts the subagent running and returns immediately with a task_id.
        Use wait_for_result() to get the completed result.

        Args:
            goal: The goal/task for the subagent to accomplish.
            context: Additional context dict passed to the subagent.
            max_iterations: Max tool-calling turns for the subagent (default: 20).
            toolsets: Toolsets to enable. Defaults to parent's toolsets.
            deterministic: Whether to use deterministic seeding (default: True).

        Returns:
            task_id: A unique string ID for this subagent task.
                   Use wait_for_result(task_id) to get the result.
        """
        task_id = str(uuid.uuid4())

        # Import here to avoid circular imports
        import model_tools as _model_tools

        # Save parent tool names before child construction mutates the global
        _parent_tool_names = list(_model_tools._last_resolved_tool_names)

        try:
            child = self._build_child_agent(
                task_id=task_id,
                goal=goal,
                context=context,
                max_iterations=max_iterations,
                toolsets=toolsets,
                deterministic=deterministic,
            )
            child._delegate_saved_tool_names = _parent_tool_names
        finally:
            # Restore parent's tool names after child construction
            _model_tools._last_resolved_tool_names = _parent_tool_names

        # Register child
        self.active_subagents[task_id] = child

        # Start running in background
        asyncio.create_task(self._run_and_record(task_id, child, goal))

        return task_id

    async def spawn_async(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        max_iterations: int = 20,
        toolsets: Optional[List[str]] = None,
        deterministic: bool = True,
    ) -> str:
        """
        Spawn a subagent to work on a goal (async version).

        Args:
            goal: The goal/task for the subagent to accomplish.
            context: Additional context dict passed to the subagent.
            max_iterations: Max tool-calling turns for the subagent (default: 20).
            toolsets: Toolsets to enable. Defaults to parent's toolsets.
            deterministic: Whether to use deterministic seeding (default: True).

        Returns:
            task_id: A unique string ID for this subagent task.
        """
        task_id = str(uuid.uuid4())

        import model_tools as _model_tools

        _parent_tool_names = list(_model_tools._last_resolved_tool_names)

        try:
            child = self._build_child_agent(
                task_id=task_id,
                goal=goal,
                context=context,
                max_iterations=max_iterations,
                toolsets=toolsets,
                deterministic=deterministic,
            )
            child._delegate_saved_tool_names = _parent_tool_names
        finally:
            _model_tools._last_resolved_tool_names = _parent_tool_names

        async with self._lock:
            self.active_subagents[task_id] = child

        asyncio.create_task(self._run_and_record(task_id, child, goal))

        return task_id

    async def _run_and_record(self, task_id: str, child: "AIAgent", goal: str):
        """
        Run a child agent and record its result.

        This is the async task that runs the child agent and stores
        the result in self._results when complete.
        """
        start_time = time.monotonic()

        try:
            # Run the child agent (blocking call within async context)
            result = await asyncio.get_event_loop().run_in_executor(
                None, child.run_conversation, goal
            )

            duration_ms = (time.monotonic() - start_time) * 1000

            summary = result.get("final_response") or ""
            completed = result.get("completed", False)
            interrupted = result.get("interrupted", False)
            error_msg = result.get("error")

            if interrupted:
                status = "interrupted"
            elif completed and summary:
                status = "completed"
            else:
                status = "failed"

            success = status == "completed"

            # Extract trace_id if deterministic execution was used
            trace_id = getattr(child, "_last_trace_id", None)

            subagent_result = SubagentResult(
                task_id=task_id,
                success=success,
                output=summary,
                error=error_msg if not success else None,
                duration_ms=duration_ms,
                trace_id=trace_id,
            )

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.exception(f"[subagent-{task_id[:8]}] failed")
            subagent_result = SubagentResult(
                task_id=task_id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=duration_ms,
                trace_id=None,
            )

        finally:
            # Unregister child from interrupt propagation
            async with self._lock:
                if task_id in self.active_subagents:
                    del self.active_subagents[task_id]

                if hasattr(self.parent, "_active_children"):
                    try:
                        self.parent._active_children.remove(child)
                    except ValueError:
                        pass

            # Restore parent tool names
            import model_tools as _model_tools

            saved = getattr(child, "_delegate_saved_tool_names", None)
            if isinstance(saved, list):
                _model_tools._last_resolved_tool_names = list(saved)

        # Store result
        async with self._lock:
            self._results[task_id] = subagent_result

    async def wait_for_result(self, task_id: str, timeout: float = 300) -> SubagentResult:
        """
        Wait for a subagent to complete and return its result.

        Args:
            task_id: The task ID returned by spawn().
            timeout: Maximum seconds to wait (default: 300).

        Returns:
            SubagentResult with the subagent's output/error/duration.

        Raises:
            asyncio.TimeoutError: If the subagent doesn't complete within timeout.
        """
        # Poll until the result is available or timeout
        start = time.monotonic()

        while time.monotonic() - start < timeout:
            async with self._lock:
                if task_id in self._results:
                    return self._results.pop(task_id)

            await asyncio.sleep(0.1)

        # Timeout reached
        raise asyncio.TimeoutError(f"Subagent {task_id} did not complete within {timeout}s")

    def get_active(self) -> List[str]:
        """
        Return list of active subagent task IDs.

        Returns:
            List of task_id strings for subagents that are still running.
        """
        return list(self.active_subagents.keys())

    def interrupt_all(self):
        """
        Send interrupt to all active subagents.

        This sets the interrupted flag on all child agents,
        causing their run loops to exit at the next opportunity.
        """
        for task_id, child in self.active_subagents.items():
            try:
                child._interrupted = True
                logger.info(f"Interrupted subagent {task_id[:8]}")
            except Exception as e:
                logger.warning(f"Failed to interrupt subagent {task_id[:8]}: {e}")

    def interrupt_subagent(self, task_id: str):
        """
        Interrupt a specific subagent by task_id.

        Args:
            task_id: The task ID of the subagent to interrupt.
        """
        child = self.active_subagents.get(task_id)
        if child:
            try:
                child._interrupted = True
                logger.info(f"Interrupted subagent {task_id[:8]}")
            except Exception as e:
                logger.warning(f"Failed to interrupt subagent {task_id[:8]}: {e}")
        else:
            logger.warning(f"Subagent {task_id[:8]} not found or already completed")

    def replay_from_trace(self, trace_id: str) -> Optional[SubagentResult]:
        """
        Replay a subagent's work from a saved execution trace.

        This allows deterministic replay of a previous subagent execution.
        The trace must have been saved during a previous run with the
        same goal and seed.

        Args:
            trace_id: The trace ID from a previous SubagentResult.

        Returns:
            A SubagentResult reconstructed from the trace, or None if
            the trace cannot be found/loaded.
        """
        # Try to load from session DB if available
        session_db = getattr(self.parent, "_session_db", None)
        if session_db and hasattr(session_db, "load_execution_trace"):
            try:
                trace_data = session_db.load_execution_trace(trace_id)
                if trace_data:
                    return SubagentResult(
                        task_id=trace_data.get("task_id", trace_id),
                        success=trace_data.get("success", False),
                        output=trace_data.get("output"),
                        error=trace_data.get("error"),
                        duration_ms=trace_data.get("duration_ms", 0),
                        trace_id=trace_id,
                    )
            except Exception as e:
                logger.warning(f"Failed to load trace {trace_id}: {e}")

        return None


# Import json for context serialization
import json
