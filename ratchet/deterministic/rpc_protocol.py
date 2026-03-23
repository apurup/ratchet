"""
RPC Protocol for Verified Subagent Communication.

Defines how parent agents and subagents communicate results,
including serialized traces and aggregated lessons.
"""

import json
import pickle
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class RPCMessage:
    """Message types for parent↔subagent RPC."""

    RESULT = "result"       # Subagent → Parent: final result
    TRACE = "trace"        # Subagent → Parent: execution trace
    LESSON = "lesson"      # Subagent → Parent: learned repair lesson
    PROGRESS = "progress"  # Subagent → Parent: intermediate progress
    INTERRUPT = "interrupt"  # Parent → Subagent: cancel task
    PING = "ping"          # Parent → Subagent: health check
    PONG = "pong"          # Subagent → Parent: health check response


@dataclass
class RPCResult:
    """
    Structured result message from subagent to parent.

    Attributes:
        type: Message type (RESULT, TRACE, LESSON, PROGRESS).
        task_id: Unique identifier for the subagent task.
        payload: JSON-serializable payload data.
    """

    type: str
    task_id: str
    payload: Any

    def serialize(self) -> bytes:
        """Serialize the RPC result to bytes using pickle."""
        return pickle.dumps(self)

    @staticmethod
    def deserialize(data: bytes) -> "RPCResult":
        """Deserialize bytes back to an RPCResult."""
        return pickle.loads(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": self.type,
            "task_id": self.task_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RPCResult":
        """Create an RPCResult from a dict."""
        return cls(
            type=data["type"],
            task_id=data["task_id"],
            payload=data["payload"],
        )


@dataclass
class RPCProgress:
    """
    Progress update message from subagent to parent.

    Attributes:
        task_id: The subagent task ID.
        step: Current step number.
        total_steps: Total expected steps (if known).
        message: Human-readable progress message.
        tool_name: Name of the tool currently executing (if any).
        tool_preview: Brief preview of tool input/output (if any).
    """

    task_id: str
    step: int
    total_steps: Optional[int] = None
    message: str = ""
    tool_name: Optional[str] = None
    tool_preview: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """Convert to a dict suitable for RPCResult payload."""
        return {
            "step": self.step,
            "total_steps": self.total_steps,
            "message": self.message,
            "tool_name": self.tool_name,
            "tool_preview": self.tool_preview,
        }


@dataclass
class RPCLesson:
    """
    Learned repair lesson message from subagent to parent.

    Attributes:
        task_id: The subagent task ID.
        failure_pattern: Description of the failure pattern observed.
        error_signature: Unique signature of the error (for matching).
        repair_strategy: The strategy that worked to fix this error.
        context: Additional context about when this lesson applies.
    """

    task_id: str
    failure_pattern: str
    error_signature: str
    repair_strategy: str
    context: Optional[Dict[str, Any]] = None

    def to_payload(self) -> Dict[str, Any]:
        """Convert to a dict suitable for RPCResult payload."""
        return {
            "failure_pattern": self.failure_pattern,
            "error_signature": self.error_signature,
            "repair_strategy": self.repair_strategy,
            "context": self.context or {},
        }


@dataclass
class RPCInterrupt:
    """
    Interrupt message from parent to subagent.

    Attributes:
        task_id: The subagent task ID to interrupt.
        reason: Human-readable reason for the interrupt.
        graceful: If True, subagent should finish current step before stopping.
    """

    task_id: str
    reason: str = ""
    graceful: bool = True

    def serialize(self) -> bytes:
        """Serialize the interrupt message."""
        return pickle.dumps(self)

    @staticmethod
    def deserialize(data: bytes) -> "RPCInterrupt":
        """Deserialize bytes to an RPCInterrupt."""
        return pickle.loads(data)


class RPCChannel:
    """
    Bidirectional RPC channel for parent↔subagent communication.

    Supports:
    - Sending structured messages (RESULT, PROGRESS, LESSON, etc.)
    - Receiving messages
    - Serialization/deserialization for transport

    This is a base class that can be extended for different transports
    (in-memory, Unix socket, HTTP, etc.).
    """

    def __init__(self):
        self._listeners: Dict[str, list] = {
            RPCMessage.RESULT: [],
            RPCMessage.TRACE: [],
            RPCMessage.LESSON: [],
            RPCMessage.PROGRESS: [],
            RPCMessage.INTERRUPT: [],
            RPCMessage.PING: [],
            RPCMessage.PONG: [],
        }

    def send(self, message: RPCResult):
        """
        Send an RPCResult message.

        Args:
            message: The RPCResult to send.
        """
        raise NotImplementedError("Subclasses must implement send()")

    def receive(self, timeout: Optional[float] = None) -> Optional[RPCResult]:
        """
        Receive an RPCResult message.

        Args:
            timeout: Maximum seconds to wait. None = blocking.

        Returns:
            The received RPCResult, or None if timeout reached.
        """
        raise NotImplementedError("Subclasses must implement receive()")

    def on(self, message_type: str, callback: callable):
        """
        Register a callback for a message type.

        Args:
            message_type: One of RPCMessage.* types.
            callback: Function to call with the received RPCResult.
        """
        if message_type in self._listeners:
            self._listeners[message_type].append(callback)
        else:
            raise ValueError(f"Unknown message type: {message_type}")

    def off(self, message_type: str, callback: callable):
        """
        Unregister a callback.

        Args:
            message_type: One of RPCMessage.* types.
            callback: The callback to remove.
        """
        if message_type in self._listeners and callback in self._listeners[message_type]:
            self._listeners[message_type].remove(callback)

    def _dispatch(self, message: RPCResult):
        """
        Dispatch a received message to registered listeners.

        Args:
            message: The received RPCResult.
        """
        listeners = self._listeners.get(message.type, [])
        for listener in listeners:
            try:
                listener(message)
            except Exception as e:
                # Don't let listener errors break the channel
                import logging
                logging.getLogger(__name__).warning(
                    f"Listener error for {message.type}: {e}"
                )


class InMemoryChannel(RPCChannel):
    """
    In-memory RPC channel for parent↔subagent within the same process.

    Uses asyncio queues for async communication.
    """

    def __init__(self):
        super().__init__()
        self._send_queue: Any = None  # Set by parent when creating channel
        self._receive_queue: Any = None  # Set by parent when creating channel

    def send(self, message: RPCResult):
        """Send a message to the channel."""
        if self._send_queue is None:
            raise RuntimeError("Channel not connected")
        try:
            self._send_queue.put_nowait(message)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to send message: {e}")

    def receive(self, timeout: Optional[float] = None) -> Optional[RPCResult]:
        """Receive a message from the channel."""
        if self._receive_queue is None:
            raise RuntimeError("Channel not connected")
        try:
            if timeout is None:
                return self._receive_queue.get_nowait()
            else:
                return self._receive_queue.get(timeout=timeout)
        except Exception:
            return None


class RPCAggregator:
    """
    Aggregates RPC messages from multiple subagents.

    Useful for batch subagent spawning where the parent wants to
    collect results from multiple children efficiently.
    """

    def __init__(self):
        self._results: Dict[str, RPCResult] = {}
        self._pending: set = set()
        self._completed_count = 0

    def add_pending(self, task_id: str):
        """Mark a task as pending."""
        self._pending.add(task_id)

    def add_result(self, result: RPCResult):
        """Record a result from a subagent."""
        self._results[result.task_id] = result
        self._pending.discard(result.task_id)
        self._completed_count += 1

    def is_complete(self) -> bool:
        """Check if all pending tasks have completed."""
        return len(self._pending) == 0

    def get_result(self, task_id: str) -> Optional[RPCResult]:
        """Get a specific result by task_id."""
        return self._results.get(task_id)

    def get_all_results(self) -> Dict[str, RPCResult]:
        """Get all results collected so far."""
        return dict(self._results)

    def get_pending(self) -> set:
        """Get the set of pending task IDs."""
        return set(self._pending)

    def completed_count(self) -> int:
        """Number of tasks completed."""
        return self._completed_count
