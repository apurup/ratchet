"""
Batch Trajectory Generation Pipeline for Hermes-Ratchet.

Generates training trajectories using the deterministic agent loop,
compresses them, and outputs them for RL training.
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# Try to import the trajectory compressor if available
try:
    from trajectory_compressor import (
        TrajectoryCompressor,
        CompressionConfig,
        TrajectoryMetrics,
    )
    HAS_COMPRESSOR = True
except ImportError:
    HAS_COMPRESSOR = False
    logger.warning("trajectory_compressor not available, compression will be skipped")


@dataclass
class TrajectoryStep:
    """
    A single step in a trajectory.

    Attributes:
        input: The input/prompt for this step.
        output: The model's output for this step.
        tool_calls: List of tool calls made (if any).
        reward: Optional reward signal (for RL training).
        trace_id: Unique trace ID for this execution.
    """

    input: str
    output: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    reward: Optional[float] = None
    trace_id: str = ""


@dataclass
class Trajectory:
    """
    A complete trajectory for a task.

    Attributes:
        task: The original task description.
        steps: List of TrajectorySteps.
        trace_id: Unique trace ID for the entire trajectory.
        metadata: Additional metadata about the trajectory.
    """

    task: str
    steps: List[TrajectoryStep] = field(default_factory=list)
    trace_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "task": self.task,
            "steps": [
                {
                    "input": s.input,
                    "output": s.output,
                    "tool_calls": s.tool_calls,
                    "reward": s.reward,
                    "trace_id": s.trace_id,
                }
                for s in self.steps
            ],
            "trace_id": self.trace_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trajectory":
        """Create a Trajectory from a dict."""
        return cls(
            task=data["task"],
            steps=[TrajectoryStep(**s) for s in data.get("steps", [])],
            trace_id=data.get("trace_id", ""),
            metadata=data.get("metadata", {}),
        )


class TrajectoryPipeline:
    """
    Generate and compress trajectories for model training.

    Pipeline stages:
    1. Run deterministic agent on batch of tasks
    2. Collect execution traces
    3. Compress trajectories (remove redundant tool call noise)
    4. Output as training-ready JSONL

    The pipeline uses the deterministic subagent manager to ensure
    reproducible trajectories, making it suitable for RL training
    where bit-exact replay is valuable.
    """

    def __init__(
        self,
        agent_factory: Callable[[], "AIAgent"],
        compression_config: Optional["CompressionConfig"] = None,
    ):
        """
        Initialize the trajectory pipeline.

        Args:
            agent_factory: A callable that returns a fresh AIAgent instance.
                          Called once per task to ensure clean state.
            compression_config: Optional config for trajectory compression.
                               If None, compression is skipped.
        """
        self.agent_factory = agent_factory
        self.compression_config = compression_config
        self._compressor: Optional["TrajectoryCompressor"] = None

        if compression_config and HAS_COMPRESSOR:
            try:
                self._compressor = TrajectoryCompressor(compression_config)
            except Exception as e:
                logger.warning(f"Failed to initialize compressor: {e}")

    async def generate_trajectories(
        self,
        tasks: List[str],
        max_workers: int = 4,
        deterministic: bool = True,
        max_iterations: int = 20,
    ) -> List[List[TrajectoryStep]]:
        """
        Run batch tasks in parallel, return trajectories.

        Args:
            tasks: List of task descriptions to run.
            max_workers: Maximum parallel subagents (default: 4).
            deterministic: Whether to use deterministic seeding (default: True).
            max_iterations: Max iterations per subagent (default: 20).

        Returns:
            List of trajectories, one per task. Each trajectory is a list
            of TrajectorySteps.
        """
        if not tasks:
            return []

        # Create subagent manager for this batch
        parent_agent = self.agent_factory()
        from ratchet.deterministic.subagent_manager import SubagentManager

        manager = SubagentManager(parent_agent)

        # Spawn all tasks
        task_ids = []
        for task in tasks:
            task_id = await manager.spawn_async(
                goal=task,
                max_iterations=max_iterations,
                deterministic=deterministic,
            )
            task_ids.append(task_id)

        # Collect results with timeout
        trajectories: List[Optional[List[TrajectoryStep]]] = [None] * len(tasks)
        timeout_per_task = 300.0  # 5 minutes per task

        async def collect_task(index: int, task_id: str, task: str):
            try:
                result = await manager.wait_for_result(task_id, timeout=timeout_per_task)
                steps = self._result_to_steps(task, result)
                trajectories[index] = steps
            except asyncio.TimeoutError:
                logger.warning(f"Task {task_id} timed out after {timeout_per_task}s")
                trajectories[index] = [
                    TrajectoryStep(
                        input=task,
                        output="",
                        tool_calls=[],
                        reward=0.0,
                        trace_id=task_id,
                    )
                ]
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                trajectories[index] = [
                    TrajectoryStep(
                        input=task,
                        output=f"Error: {e}",
                        tool_calls=[],
                        reward=0.0,
                        trace_id=task_id,
                    )
                ]

        # Run all collections concurrently (limited by max_workers semaphore)
        semaphore = asyncio.Semaphore(max_workers)

        async def bounded_collect(index: int, task_id: str, task: str):
            async with semaphore:
                await collect_task(index, task_id, task)

        await asyncio.gather(
            *[bounded_collect(i, tid, task) for i, (tid, task) in enumerate(zip(task_ids, tasks))]
        )

        return [t for t in trajectories if t is not None]

    def _result_to_steps(self, task: str, result: "SubagentResult") -> List[TrajectoryStep]:
        """Convert a SubagentResult to a list of TrajectorySteps."""
        # For now, create a single step from the result
        # In a full implementation, we would parse the intermediate steps
        # from the subagent's conversation history
        return [
            TrajectoryStep(
                input=task,
                output=result.output or "",
                tool_calls=[],
                reward=1.0 if result.success else 0.0,
                trace_id=result.trace_id or result.task_id,
            )
        ]

    def compress_trajectory(
        self,
        steps: List[TrajectoryStep],
        target_max_tokens: int = 15250,
    ) -> List[Dict[str, Any]]:
        """
        Remove redundant tool call sequences, keep decision points.

        This applies heuristics to compress a trajectory:
        1. Merge consecutive tool calls of the same type
        2. Remove intermediate steps that don't affect the final outcome
        3. Keep only decision points (branching, verification, etc.)

        Args:
            steps: The trajectory steps to compress.
            target_max_tokens: Token budget target for compressed output.

        Returns:
            List of compressed step dicts suitable for JSONL export.
        """
        if not steps:
            return []

        # If we have the full compressor available, use it
        if self._compressor and HAS_COMPRESSOR:
            return self._compress_with_compressor(steps, target_max_tokens)

        # Fallback: simple heuristic compression
        return self._compress_simple(steps)

    def _compress_with_compressor(
        self,
        steps: List[TrajectoryStep],
        target_max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """Use the full TrajectoryCompressor for compression."""
        # Convert TrajectorySteps to the format expected by TrajectoryCompressor
        # (list of dicts with "from" and "value" keys)
        trajectory_format = []
        for step in steps:
            trajectory_format.append({"from": "human", "value": step.input})
            trajectory_format.append({"from": "gpt", "value": step.output})
            for tc in step.tool_calls:
                trajectory_format.append(
                    {"from": "tool", "value": json.dumps(tc)}
                )

        # Compress
        compressed, _ = self._compressor.compress_trajectory(trajectory_format)

        # Convert back to our format
        result = []
        for turn in compressed:
            result.append(
                {
                    "input": turn.get("from") == "human" and turn.get("value") or "",
                    "output": turn.get("from") == "gpt" and turn.get("value") or "",
                    "tool_calls": [],
                    "reward": None,
                    "trace_id": steps[0].trace_id if steps else "",
                }
            )

        return result

    def _compress_simple(self, steps: List[TrajectoryStep]) -> List[Dict[str, Any]]:
        """Simple heuristic compression without full compressor."""
        if not steps:
            return []

        compressed = []

        # Always keep first step (task input)
        if steps:
            first = steps[0]
            compressed.append({
                "input": first.input,
                "output": first.output,
                "tool_calls": first.tool_calls,
                "reward": first.reward,
                "trace_id": first.trace_id,
            })

        # Keep last step (final output)
        if len(steps) > 1:
            last = steps[-1]
            compressed.append({
                "input": last.input,
                "output": last.output,
                "tool_calls": last.tool_calls,
                "reward": last.reward,
                "trace_id": last.trace_id,
            })

        # Keep steps with non-empty tool_calls (decision/action points)
        for step in steps[1:-1]:
            if step.tool_calls:
                compressed.append({
                    "input": step.input,
                    "output": step.output,
                    "tool_calls": step.tool_calls,
                    "reward": step.reward,
                    "trace_id": step.trace_id,
                })

        return compressed

    def export_jsonl(
        self,
        trajectories: List[List[TrajectoryStep]],
        path: str,
        include_metadata: bool = True,
    ):
        """
        Export trajectories as JSONL for RL training.

        Each line in the output file contains one trajectory as a JSON object.

        Args:
            trajectories: List of trajectories to export.
            path: Output file path.
            include_metadata: Whether to include metadata (timestamp, etc.).
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for trajectory in trajectories:
                # Compress the trajectory
                compressed = self.compress_trajectory(trajectory)

                # Build export record
                record = {
                    "task": trajectory[0].input if trajectory else "",
                    "steps": compressed,
                    "trace_id": trajectory[0].trace_id if trajectory else "",
                }

                if include_metadata:
                    record["metadata"] = {
                        "exported_at": datetime.now().isoformat(),
                        "num_steps_original": len(trajectory),
                        "num_steps_compressed": len(compressed),
                    }

                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"Exported {len(trajectories)} trajectories to {path}")

    def export_jsonl_from_dicts(
        self,
        trajectories: List[List[Dict[str, Any]]],
        path: str,
        include_metadata: bool = True,
    ):
        """
        Export trajectories from dict format as JSONL for RL training.

        This variant accepts plain dicts instead of TrajectoryStep objects,
        useful when loading from existing files.

        Args:
            trajectories: List of trajectory dicts.
            path: Output file path.
            include_metadata: Whether to include metadata.
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for trajectory in trajectories:
                record = {
                    "task": trajectory[0].get("input", "") if trajectory else "",
                    "steps": trajectory,
                    "trace_id": trajectory[0].get("trace_id", "") if trajectory else "",
                }

                if include_metadata:
                    record["metadata"] = {
                        "exported_at": datetime.now().isoformat(),
                        "num_steps": len(trajectory),
                    }

                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"Exported {len(trajectories)} trajectories to {path}")


# Import SubagentResult for type hints
from ratchet.deterministic.subagent_manager import SubagentResult
