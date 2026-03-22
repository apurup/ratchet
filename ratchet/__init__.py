"""
Ratchet - Deterministic self-improving AI agent framework
"""

__version__ = "0.1.0"

# Core exports
from ratchet.models import ModelResponse, ModelClient, get_client
from ratchet.skill import Skill, Step, StepType, VerificationRule, VerificationType
from ratchet.generator import Generator, GenerationResult
from ratchet.verifier import Verifier, VerificationResult, Sandbox
from ratchet.reflector import Reflector, Reflection, FailureRecord
from ratchet.curator import Curator, KnowledgeEntry
from ratchet.agent import Agent, AgentConfig, StepResult, ExecutionResult

__all__ = [
    # Version
    "__version__",
    # Models
    "ModelResponse",
    "ModelClient",
    "get_client",
    # Skill schema
    "Skill",
    "Step",
    "StepType",
    "VerificationRule",
    "VerificationType",
    # Generator
    "Generator",
    "GenerationResult",
    # Verifier
    "Verifier",
    "VerificationResult",
    "Sandbox",
    # Reflector
    "Reflector",
    "Reflection",
    "FailureRecord",
    # Curator
    "Curator",
    "KnowledgeEntry",
    # Agent
    "Agent",
    "AgentConfig",
    "StepResult",
    "ExecutionResult",
]
