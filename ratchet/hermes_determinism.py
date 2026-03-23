"""
Deterministic execution infrastructure for Hermes-Ratchet.

Provides:
- Seed computation: derive a deterministic seed from (task + skill_name)
- DeterministicReplay: capture step outputs during forward pass, replay on replay pass
- Seeding utilities: set Python random state from a seed for reproducible tool-call ordering
- Integration points for AIAgent

Usage:
    from hermes_determinism import compute_seed, DeterministicReplay

    seed = compute_seed("fix the fizzbuzz function", skill_name="code_repair")
    dr = DeterministicReplay(seed)

    # During forward pass:
    dr.capture(f"terminal:{args_hash}", output_result)

    # During replay:
    cached = dr.replay(f"terminal:{args_hash}")  # returns cached instead of re-executing
"""

import hashlib
import pickle
import random
import threading
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List


def compute_seed(task: str, skill_name: Optional[str] = None) -> int:
    """
    Derive a deterministic 64-bit seed from task + skill_name.

    Uses SHA256 Truncated to 64 bits. The seed is stable across runs and
    Python versions (unlike hash() which is randomized in Python 3.3+).

    seed = int(SHA256(task:skill_name)[:16], 16) % 2^63  (positive int)

    Args:
        task: The task description or user message.
        skill_name: Optional skill name for skill-scoped determinism.

    Returns:
        A positive 64-bit integer suitable for random.seed().
    """
    data = f"{task}:{skill_name or ''}".encode("utf-8")
    raw = hashlib.sha256(data).hexdigest()[:16]
    seed_value = int(raw, 16)
    # Keep it positive and within 64-bit range
    return seed_value % (2**63)


@dataclass
class StepTrace:
    """Record of a single step's execution during a forward pass."""
    step_key: str          # e.g. "terminal:{json_args_hash}"
    output: str            # Serialized JSON result
    success: bool
    duration_ms: float
    tool_name: str


@dataclass
class DeterministicState:
    """Immutable snapshot of all captured state needed for replay."""
    seed: int
    step_traces: List[StepTrace] = field(default_factory=list)
    random_state: Optional[tuple] = None  # random.getstate() tuple, None if not captured


class DeterministicReplay:
    """
    Captures step outputs during forward execution and replays them deterministically.

    Thread-safe for recording. The replay mode is set once at construction and
    never changes.
    """

    def __init__(self, seed: int, step_traces: List[StepTrace] = None, random_state: Optional[tuple] = None):
        self.seed = seed
        self._traces: Dict[str, StepTrace] = {}
        if step_traces:
            for st in step_traces:
                self._traces[st.step_key] = st
        self._random_state = random_state
        # _is_replay is True only if random_state was actually captured (non-None and non-empty)
        self._is_replay = random_state is not None and len(random_state) > 0
        self._lock = threading.Lock()

    def capture(self, step_key: str, output: str, success: bool = True, duration_ms: float = 0.0, tool_name: str = ""):
        """Record a step's output during the forward pass."""
        trace = StepTrace(
            step_key=step_key,
            output=output,
            success=success,
            duration_ms=duration_ms,
            tool_name=tool_name,
        )
        with self._lock:
            self._traces[step_key] = trace

    def replay(self, step_key: str) -> Optional[str]:
        """
        Return the cached output for a step during replay.

        Returns None if the step_key was not captured (non-deterministic step
        or external API call that must be re-executed normally).
        """
        if not self._is_replay:
            return None
        trace = self._traces.get(step_key)
        return trace.output if trace else None

    def has_cached(self, step_key: str) -> bool:
        """Check if a step has been cached (for replay only)."""
        return step_key in self._traces

    @property
    def is_replay(self) -> bool:
        """True if this instance was deserialized from stored state (replay mode)."""
        return self._is_replay

    def get_random_state(self) -> Optional[tuple]:
        """Return the captured random state tuple for restoration during replay."""
        return self._random_state

    def serialize(self) -> bytes:
        """Serialize state for storage in SessionDB."""
        state = DeterministicState(
            seed=self.seed,
            step_traces=list(self._traces.values()),
            random_state=self._random_state,
        )
        return pickle.dumps(state)

    @staticmethod
    def deserialize(data: bytes) -> "DeterministicReplay":
        """Restore from stored bytes."""
        state: DeterministicState = pickle.loads(data)
        return DeterministicReplay(
            seed=state.seed,
            step_traces=state.step_traces,
            random_state=state.random_state,
        )


def step_key(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Build a stable key for a tool call's arguments.

    Used as the cache key in DeterministicReplay.capture()/replay().
    JSON serialization ensures ordering consistency across processes.
    """
    import json
    args_str = json.dumps(args, sort_keys=True, default=str)
    args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:16]
    return f"{tool_name}:{args_hash}"


class HermesDeterminismMixin:
    """
    Mixin that adds deterministic replay capability to AIAgent.

    Adds to AIAgent:
    - self._deterministic_seed: Optional[int]
    - self._deterministic_replay: Optional[DeterministicReplay]
    - self._deterministic_state: Optional[DeterministicState]
    - self.compute_seed(task, skill_name)
    - self.is_replay() -> bool
    - self.capture_step(key, output, ...)
    - self.replay_step(key) -> Optional[str]

    Usage:
        class MyAgent(HermesDeterminismMixin, AIAgent):
            ...
    """

    def init_determinism(self, seed: Optional[int] = None, replay_data: Optional[bytes] = None):
        """
        Initialize deterministic mode.

        Args:
            seed: Explicit seed. If None and replay_data is None, determinism is disabled.
            replay_data: Serialized DeterministicReplay bytes from a prior run.
                If provided, seed is ignored and replay mode is activated.
        """
        if replay_data:
            self._deterministic_replay = DeterministicReplay.deserialize(replay_data)
            self._deterministic_seed = self._deterministic_replay.seed
        elif seed is not None:
            self._deterministic_seed = seed
            self._deterministic_replay = DeterministicReplay(seed)
        else:
            self._deterministic_seed = None
            self._deterministic_replay = None

    def compute_deterministic_seed(self, task: str, skill_name: Optional[str] = None) -> int:
        """Compute and store a seed for the given task."""
        self._deterministic_seed = compute_seed(task, skill_name)
        self._deterministic_replay = DeterministicReplay(self._deterministic_seed)
        return self._deterministic_seed

    def is_replay(self) -> bool:
        return self._deterministic_replay is not None and self._deterministic_replay.is_replay

    def capture_step(self, step_key: str, output: str, success: bool = True, duration_ms: float = 0.0, tool_name: str = ""):
        """Record a step's output during forward pass."""
        if self._deterministic_replay:
            self._deterministic_replay.capture(step_key, output, success, duration_ms, tool_name)

    def replay_step(self, step_key: str) -> Optional[str]:
        """Return cached output if in replay mode, None otherwise."""
        if self._deterministic_replay:
            return self._deterministic_replay.replay(step_key)
        return None

    def get_deterministic_state(self) -> Optional[DeterministicState]:
        """Return the current deterministic state for serialization."""
        if not self._deterministic_replay:
            return None
        return DeterministicState(
            seed=self._deterministic_seed,
            step_traces=list(self._deterministic_replay._traces.values()),
            random_state=random.getstate(),
        )

    def serialize_deterministic_state(self) -> Optional[bytes]:
        """Serialize deterministic state for storage."""
        state = self.get_deterministic_state()
        if not state:
            return None
        return pickle.dumps(state)

    def restore_random_state(self):
        """Restore the random state from the captured replay state."""
        if self._deterministic_replay and self._deterministic_replay._random_state:
            random.setstate(self._deterministic_replay._random_state)

    def learn_from_failure(
        self,
        failure_pattern: str,
        error_signature: str,
        repair_strategy: str,
        context: str,
    ):
        """
        After a failed task, record a repair lesson in Curator.

        This is the integration point between deterministic execution
        (which detects failures) and the Curator knowledge base
        (which stores repair lessons for future reuse).

        Args:
            failure_pattern: What kind of failure (e.g. "syntax_error", "logic_bug")
            error_signature: Specific error message or signature
            repair_strategy: How it was fixed
            context: Broader context (task description, skill name, etc.)
        """
        try:
            from ratchet.deterministic.curator import HermesCurator
            curator = HermesCurator()
            curator.add_lesson(
                failure_pattern=failure_pattern,
                error_signature=error_signature,
                context=context,
                repair_strategy=repair_strategy,
            )
        except Exception as e:
            # Non-fatal: curator failures should not crash the agent loop
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to record repair lesson: {e}"
            )
