"""
LangSmith tracing helper.

This module keeps LangSmith integration optional:
- If LANGSMITH_TRACING is false/missing, tracing is disabled.
- If langsmith package is missing, tracing is disabled gracefully.
- If API key is missing, tracing is disabled gracefully.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional


class LangSmithTracer:
    """Small wrapper around LangSmith trace context manager."""

    def __init__(self) -> None:
        self.enabled_flag = os.getenv("LANGSMITH_TRACING", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.api_key = os.getenv("LANGSMITH_API_KEY")
        self.project = os.getenv("LANGSMITH_PROJECT", "code-intelligence-platform")
        self.endpoint = os.getenv("LANGSMITH_ENDPOINT")

        self._trace_fn = None
        self._enabled = False

        if not self.enabled_flag:
            return
        if not self.api_key:
            print("LangSmith tracing requested but LANGSMITH_API_KEY is missing.")
            return

        try:
            from langsmith.run_helpers import trace  # type: ignore

            self._trace_fn = trace
            # Keep env vars aligned with LangSmith SDK defaults.
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_API_KEY"] = self.api_key
            os.environ["LANGSMITH_PROJECT"] = self.project
            if self.endpoint:
                os.environ["LANGSMITH_ENDPOINT"] = self.endpoint
            self._enabled = True
        except Exception as e:
            print(f"LangSmith tracing disabled (langsmith import failed): {e}")

    def is_enabled(self) -> bool:
        """Whether tracing is active."""
        return self._enabled and self._trace_fn is not None

    def get_status(self) -> Dict[str, Any]:
        """Status payload for diagnostics and health checks."""
        return {
            "enabled": self.is_enabled(),
            "project": self.project if self.is_enabled() else None,
            "endpoint": self.endpoint if self.is_enabled() else None,
        }

    @contextmanager
    def trace(
        self,
        name: str,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Generator[None, None, None]:
        """
        Create a LangSmith trace span when enabled, otherwise no-op.
        """
        if not self.is_enabled():
            yield
            return

        trace_kwargs = {
            "name": name,
            "inputs": inputs or {},
            "metadata": metadata or {},
            "tags": tags or [],
            "project_name": self.project,
        }
        with self._trace_fn(**trace_kwargs):  # type: ignore[misc]
            yield

