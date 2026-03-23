"""
Verified Memory Writes for Ratchet.

When the agent writes to MEMORY.md or USER.md, this module intercepts the write,
validates it through a temp file, and only commits if verification passes.

Verification checks:
- No prompt injection patterns
- No invisible unicode / bidirectional attacks
- No secret exfiltration patterns
- Valid markdown syntax
"""

import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VerificationStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class VerificationResult:
    """Result of a memory verification check."""
    status: VerificationStatus
    message: str
    file_path: Optional[str] = None


# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    # Markdown/image-based injections
    re.compile(r'\]\(https?://', re.IGNORECASE),
    # Self-referential prompt attempts
    re.compile(r'ignore (all |previous |system |)instructions?', re.IGNORECASE),
    re.compile(r'ignore (all |previous |)commands?', re.IGNORECASE),
    re.compile(r'forget (all |previous |)instructions?', re.IGNORECASE),
    re.compile(r'disregard (your |the |)system', re.IGNORECASE),
    re.compile(r'you (are now |should )?act as', re.IGNORECASE),
    re.compile(r'(system|assistant|user) role', re.IGNORECASE),
    # Prompt extraction attempts
    re.compile(r'repeat (your |the |)system prompt', re.IGNORECASE),
    re.compile(r'show (me |your |)instructions', re.IGNORECASE),
    re.compile(r'output (your |the |)prompt', re.IGNORECASE),
    # Override attempts
    re.compile(r'(instead|instead of) following.*instructions', re.IGNORECASE),
    re.compile(r'do not (follow|obey|use) (these |any |)instructions', re.IGNORECASE),
    # Jailbreak patterns
    re.compile(r'\bDAN\b', re.IGNORECASE),
    re.compile(r'jailbreak', re.IGNORECASE),
    re.compile(r'new (system|AI|AI assistant) (prompt|instruction|rule)', re.IGNORECASE),
    # Embedded instructions in code blocks
    re.compile(r'```system', re.IGNORECASE),
    re.compile(r'```instructions', re.IGNORECASE),
]

# Patterns that indicate secret exfiltration attempts
EXFIL_PATTERNS = [
    re.compile(r'extract.*(password|secret|token|api.?key|credential)', re.IGNORECASE),
    re.compile(r'send.*(data|info|content|memory).*to.*(url|server|web|http)', re.IGNORECASE),
    re.compile(r'(password|secret|token|api.?key)\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
]

# Invisible / bidirectional unicode characters
INVISIBLE_UNICODE_PATTERNS = [
    # Zero-width characters
    re.compile(r'[\u200b-\u200f\ufeff]'),
    # Bidirectional overrides
    re.compile(r'[\u202a-\u202e\u2066-\u2069]'),
    # Other invisible characters
    re.compile(r'[\u00ad\u2003\u2002]'),
    # Object replacement
    re.compile(r'[\ufffc\ufffd]'),
]

# Markdown syntax structural elements that should be balanced
MARKDOWN_STRUCTURAL = [
    ('```', '```'),  # code fences
    ('[', ']'),      # links
    ('<', '>'),      # HTML tags
]


class MemoryVerifier:
    """
    Verifies memory writes before they are committed to disk.

    Write flow:
    1. Content written to a temp file
    2. Verification checks run against the temp file
    3. On PASS: copy temp file to real destination
    4. On FAIL: raise VerificationError, temp file is discarded
    """

    def __init__(self, verifier_module=None):
        """
        Initialize the memory verifier.

        Args:
            verifier_module: Optional module to delegate code verification to
                            (e.g. deterministic.verifier). If None, only
                            pattern-based checks are performed.
        """
        self._verifier_module = verifier_module

    async def verify_memory_write(
        self,
        file_path: str,
        new_content: str,
    ) -> VerificationResult:
        """
        Write content to temp file, verify it's valid and safe, then commit.

        Args:
            file_path: Destination path (MEMORY.md, USER.md, etc.)
            new_content: The content to write

        Returns:
            VerificationResult with PASS/FAIL status

        Raises:
            VerificationError: If verification fails
        """
        # Determine if this file should be verified
        if not self._should_verify(file_path):
            return VerificationResult(
                status=VerificationStatus.SKIP,
                message=f"Skipping verification for {file_path}",
                file_path=file_path,
            )

        # 1. Write to temp file
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.md',
                delete=False,
            ) as tf:
                tf.write(new_content)
                temp_path = tf.name

            # 2. Run verification checks
            result = await self._verify_file(temp_path, new_content)

            if result.status == VerificationStatus.FAIL:
                logger.error(f"Memory verification failed for {file_path}: {result.message}")
                raise VerificationError(result.message)

            # 3. On PASS: copy to real file
            if result.status == VerificationStatus.PASS:
                os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
                shutil.copy2(temp_path, file_path)
                logger.info(f"Memory write verified and committed to {file_path}")
                return VerificationResult(
                    status=VerificationStatus.PASS,
                    message=f"Verified and committed to {file_path}",
                    file_path=file_path,
                )

            return result

        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _should_verify(self, file_path: str) -> bool:
        """Determine if a file should be verified."""
        verify_suffixes = ('MEMORY.md', 'USER.md', '.memory', '.user')
        return any(file_path.endswith(s) for s in verify_suffixes)

    async def _verify_file(self, temp_path: str, content: str) -> VerificationResult:
        """
        Run all verification checks against the temp file.

        Args:
            temp_path: Path to the temp file
            content: The content being written

        Returns:
            VerificationResult
        """
        # Check 1: Injection patterns
        if self._check_injection(content):
            return VerificationResult(
                status=VerificationStatus.FAIL,
                message="Prompt injection pattern detected in memory write",
                file_path=temp_path,
            )

        # Check 2: Invisible unicode
        if self._check_invisible_unicode(content):
            return VerificationResult(
                status=VerificationStatus.FAIL,
                message="Invisible unicode characters detected in memory write",
                file_path=temp_path,
            )

        # Check 3: Secret exfiltration
        if self._check_exfiltration(content):
            return VerificationResult(
                status=VerificationStatus.FAIL,
                message="Potential secret exfiltration pattern detected",
                file_path=temp_path,
            )

        # Check 4: Markdown syntax
        if not self._check_markdown_syntax(content):
            return VerificationResult(
                status=VerificationStatus.FAIL,
                message="Invalid markdown syntax in memory write",
                file_path=temp_path,
            )

        # Check 5: File is readable and non-empty (basic integrity)
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                message="Temp file is empty or missing",
                file_path=temp_path,
            )

        # Optional: Delegate to RatchetVerifier if available
        if self._verifier_module:
            try:
                # Try to use the verifier module for additional checks
                # This uses the same verify_code pattern but for markdown content
                verifier_result = await self._delegate_verification(temp_path, content)
                if verifier_result:
                    return verifier_result
            except Exception as e:
                logger.warning(f"Verifier module check failed (non-fatal): {e}")

        return VerificationResult(
            status=VerificationStatus.PASS,
            message="All verification checks passed",
            file_path=temp_path,
        )

    def _check_injection(self, content: str) -> bool:
        """
        Check for prompt injection patterns.

        Returns True if any injection pattern is found.
        """
        for pattern in INJECTION_PATTERNS:
            if pattern.search(content):
                return True
        return False

    def _check_invisible_unicode(self, content: str) -> bool:
        """
        Check for invisible unicode / bidirectional attacks.

        Returns True if dangerous invisible characters are found.
        """
        for pattern in INVISIBLE_UNICODE_PATTERNS:
            if pattern.search(content):
                return True
        return False

    def _check_exfiltration(self, content: str) -> bool:
        """
        Check for potential secret exfiltration patterns.

        Returns True if exfiltration patterns are found.
        """
        for pattern in EXFIL_PATTERNS:
            if pattern.search(content):
                return True
        return False

    def _check_markdown_syntax(self, content: str) -> bool:
        """
        Basic markdown syntax validation.

        Checks for:
        - Balanced code fences (```)
        - Balanced link brackets ([])
        - No unclosed structural elements at end of file that look broken

        Returns True if basic syntax is valid.
        """
        lines = content.split('\n')

        # Track code fence state
        in_code_fence = False
        code_fence_line = -1

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check for code fence open/close
            if stripped.startswith('```'):
                if not in_code_fence:
                    in_code_fence = True
                    code_fence_line = i
                else:
                    # This could be a closing fence
                    # But if the previous fence was just an open marker with no language,
                    # and this is a content line, let it pass
                    if stripped != '```':
                        # It's a closing fence
                        in_code_fence = False
                        code_fence_line = -1

            # Skip checks inside code fences
            if in_code_fence:
                continue

            # Check for link syntax - links should be balanced within a line
            # [text](url) - we just check basic balance, not full URL validation
            open_brackets = stripped.count('[')
            close_brackets = stripped.count(']')
            if open_brackets != close_brackets:
                # Allow some imbalance in the same line (may be multi-line link)
                # But flag if it looks broken
                if '](' in stripped and open_brackets < close_brackets:
                    return False

        # If code fence is still open at end of file, that's an error
        if in_code_fence:
            return False

        return True

    async def _delegate_verification(
        self,
        temp_path: str,
        content: str,
    ) -> Optional[VerificationResult]:
        """
        Delegate to RatchetVerifier if available for additional checks.

        This allows the memory verifier to leverage the same verification
        infrastructure used for code verification.
        """
        if not self._verifier_module:
            return None

        # Try to import and use RatchetVerifier.verify_code
        try:
            verifier = self._verifier_module.RatchetVerifier()
            # For memory, we treat it as text verification
            # Pass the content as the "code" to verify
            result = await verifier.verify_code(
                code=content,
                tests="",  # No tests for memory verification
                language="markdown",
                timeout=5,
            )
            # RatchetVerifier returns a VerificationResult-like object
            # Map it to our VerificationResult
            if hasattr(result, 'status'):
                status_map = {
                    'PASS': VerificationStatus.PASS,
                    'FAIL': VerificationStatus.FAIL,
                    'ERROR': VerificationStatus.FAIL,
                    'SKIP': VerificationStatus.SKIP,
                }
                mapped_status = status_map.get(str(result.status), VerificationStatus.FAIL)
                return VerificationResult(
                    status=mapped_status,
                    message=getattr(result, 'message', str(result)),
                    file_path=temp_path,
                )
        except Exception as e:
            logger.debug(f"Delegate verification skipped: {e}")

        return None


class VerificationError(Exception):
    """Raised when a memory write fails verification."""
    pass


# Convenience function for sync contexts
def verify_memory_write_sync(
    file_path: str,
    new_content: str,
    verifier_module=None,
) -> VerificationResult:
    """
    Synchronous wrapper around MemoryVerifier.verify_memory_write.

    Note: This creates a simple event loop for the async method.
    For production use, prefer the async interface.
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    verifier = MemoryVerifier(verifier_module)
    return loop.run_until_complete(
        verifier.verify_memory_write(file_path, new_content)
    )
