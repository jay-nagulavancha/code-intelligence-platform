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
            # langsmith >=0.2 moved trace to langsmith directly;
            # fall back to run_helpers for older versions
            try:
                from langsmith import trace  # type: ignore
            except ImportError:
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

    def _truncate_text(self, value: str, max_len: int = 1200) -> str:
        if len(value) <= max_len:
            return value
        return f"{value[:max_len]}... [truncated {len(value) - max_len} chars]"

    def _safe_serialize(self, value: Any, depth: int = 0) -> Any:
        """
        Convert arbitrary objects into JSON-safe, bounded structures for tracing.
        """
        if depth > 4:
            return "[max_depth_reached]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._truncate_text(value)
        if isinstance(value, (list, tuple, set)):
            seq = list(value)[:50]
            return [self._safe_serialize(v, depth + 1) for v in seq]
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for i, (k, v) in enumerate(value.items()):
                if i >= 100:
                    out["__truncated__"] = f"{len(value) - 100} more keys omitted"
                    break
                out[str(k)] = self._safe_serialize(v, depth + 1)
            return out
        return self._truncate_text(str(value))

    @contextmanager
    def trace(
        self,
        name: str,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Generator[Any, None, None]:
        """
        Create a LangSmith trace span when enabled, otherwise no-op.
        Compatible with langsmith >=0.1 and >=0.7.
        """
        if not self.is_enabled():
            yield None
            return

        try:
            with self._trace_fn(
                name,
                inputs=self._safe_serialize(inputs or {}),
                project_name=self.project,
                tags=tags or [],
                metadata=self._safe_serialize(metadata or {}),
            ) as run_tree:
                yield run_tree
        except Exception as e:
            print(f"LangSmith trace failed: {e}")
            yield None

    def record_component_io(
        self,
        name: str,
        component_input: Optional[Dict[str, Any]] = None,
        component_output: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Emit a one-shot child span capturing component input/output.
        Uses the native trace context manager directly so langsmith can
        correctly link it as a child of the current parent span.
        """
        if not self.is_enabled():
            return

        safe_input = self._safe_serialize(component_input or {})
        safe_output = self._safe_serialize(component_output or {})

        try:
            with self._trace_fn(
                name,
                inputs=safe_input if isinstance(safe_input, dict) else {"input": safe_input},
                project_name=self.project,
                tags=(tags or []) + ["component-io"],
                metadata=self._safe_serialize(metadata or {}),
            ) as run_tree:
                if run_tree is not None:
                    out = safe_output if isinstance(safe_output, dict) else {"output": safe_output}
                    run_tree.add_outputs(out)
        except Exception:
            # Never break the pipeline due to tracing failures
            pass

