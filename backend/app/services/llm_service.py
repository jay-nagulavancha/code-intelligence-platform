"""
LLM Service - Handles LLM interactions for report generation,
release notes, vulnerability suggestions, and deprecation summaries.

Supported providers:
  - ollama      : Local open-source models (default for development)
  - groq        : Free cloud inference via Groq (fastest free option)
  - openai      : OpenAI or any OpenAI-compatible API
  - huggingface : Hugging Face Inference API
  - bedrock     : AWS Bedrock models via boto3
"""
import os
import json
import sys
import time
import requests
from typing import Optional, Dict, Any, List, Union
from enum import Enum
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from app.services.langsmith_service import LangSmithTracer

try:
    from json_repair import repair_json as _repair_json
    _HAS_JSON_REPAIR = True
except Exception:
    _repair_json = None
    _HAS_JSON_REPAIR = False


def _basic_json_repair(text: str) -> str:
    """
    Best-effort JSON repair when the json_repair package is unavailable.
    Handles a few high-frequency LLM mistakes:
      - Trailing commas before } or ].
      - Truncated input that ends inside a string/array/object: closes any
        unterminated string and balances open brackets/braces.

    This is intentionally conservative; for the full set of edge cases the
    json_repair dependency does a much better job and is preferred.
    """
    s = text

    in_string = False
    escape = False
    stack: List[str] = []
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()

    if in_string:
        s += '"'

    while stack:
        s += stack.pop()

    out_chars: List[str] = []
    in_string = False
    escape = False
    for i, ch in enumerate(s):
        if escape:
            out_chars.append(ch)
            escape = False
            continue
        if ch == "\\":
            out_chars.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            out_chars.append(ch)
            continue
        if not in_string and ch == ",":
            j = i + 1
            while j < len(s) and s[j].isspace():
                j += 1
            if j < len(s) and s[j] in "}]":
                continue
        out_chars.append(ch)
    return "".join(out_chars)


def _try_parse(candidate: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
    """Try strict json.loads, then json_repair, then a basic in-house repair."""
    try:
        return json.loads(candidate)
    except Exception:
        pass

    if _HAS_JSON_REPAIR:
        try:
            repaired = _repair_json(candidate, return_objects=True)
            if isinstance(repaired, (dict, list)):
                return repaired
            if isinstance(repaired, str) and repaired:
                try:
                    return json.loads(repaired)
                except Exception:
                    pass
        except Exception:
            pass

    try:
        return json.loads(_basic_json_repair(candidate))
    except Exception:
        return None


def extract_json_from_llm(
    text: str,
    *,
    expect: str = "any",
    log_label: Optional[str] = None,
) -> Union[Dict[str, Any], List[Any]]:
    """
    Extract and parse JSON from an LLM response, tolerating common LLM mistakes.

    Handles:
      - Markdown code fences (```json ... ``` or ``` ... ```).
      - Leading/trailing prose around the JSON object/array.
      - Truncated/unterminated strings, missing commas, trailing commas, and
        unescaped inner quotes (best results when the json_repair package is
        installed; degrades gracefully without it).

    Args:
        text: Raw LLM output.
        expect: One of "object", "array", or "any". When "object" or "array"
            is passed, only candidates of the requested top-level kind are
            considered, so a malformed object never silently parses as an
            inner array (or vice versa).
        log_label: Optional label used when logging a debug snippet on failure.

    Returns:
        Parsed JSON value (dict or list).

    Raises:
        ValueError: If JSON cannot be recovered even after repair attempts.
    """
    if text is None:
        raise ValueError("LLM response was None")

    cleaned = text.strip()

    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
        if "```" in cleaned:
            cleaned = cleaned.split("```", 1)[0]
        cleaned = cleaned.strip()
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1].strip()

    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")
    arr_start = cleaned.find("[")
    arr_end = cleaned.rfind("]")

    object_candidate = (
        cleaned[obj_start : obj_end + 1]
        if obj_start != -1 and obj_end > obj_start
        else None
    )
    array_candidate = (
        cleaned[arr_start : arr_end + 1]
        if arr_start != -1 and arr_end > arr_start
        else None
    )

    if expect == "object":
        candidates = [c for c in (object_candidate, cleaned) if c]
        accept_kind = (dict,)
    elif expect == "array":
        candidates = [c for c in (array_candidate, cleaned) if c]
        accept_kind = (list,)
    else:
        prefer_arr = arr_start != -1 and (obj_start == -1 or arr_start < obj_start)
        first_two = (
            (array_candidate, object_candidate)
            if prefer_arr
            else (object_candidate, array_candidate)
        )
        candidates = [c for c in (*first_two, cleaned) if c]
        accept_kind = (dict, list)

    deduped: List[str] = []
    for c in candidates:
        if c not in deduped:
            deduped.append(c)

    for candidate in deduped:
        parsed = _try_parse(candidate)
        if isinstance(parsed, accept_kind):
            return parsed

    snippet_head = (text or "")[:500]
    snippet_tail = (text or "")[-500:] if len(text or "") > 500 else ""
    label = f" ({log_label})" if log_label else ""
    install_hint = (
        ""
        if _HAS_JSON_REPAIR
        else " (hint: install `json-repair` for better recovery from truncated/malformed LLM JSON)"
    )
    print(
        f"[llm-json] failed to parse JSON{label}{install_hint}\n"
        f"[llm-json] response head: {snippet_head!r}\n"
        f"[llm-json] response tail: {snippet_tail!r}",
        file=sys.stderr,
        flush=True,
    )
    raise ValueError(
        f"Could not parse JSON from LLM response{install_hint}"
    )


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    GROQ = "groq"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    BEDROCK = "bedrock"

    # Providers that use the OpenAI chat completions format
    _OPENAI_COMPAT = {"groq", "openai"}


class LLMService:
    """
    Service for LLM interactions. Supports multiple providers:
    - Ollama     — local, open-source, runs on your machine
    - Groq       — free cloud, blazing fast (~500 tok/s), needs free API key
    - OpenAI     — cloud, any OpenAI-compatible endpoint
    - HuggingFace — cloud, Inference API
    """

    # Default models per provider
    _DEFAULT_MODELS = {
        "ollama": "llama3.2:1b",
        "groq": "llama-3.1-8b-instant",
        "openai": "gpt-4o-mini",
        "huggingface": "mistralai/Mistral-7B-Instruct-v0.2",
        "bedrock": "anthropic.claude-3-5-sonnet-20240620-v1:0",
    }

    _DEFAULT_URLS = {
        "ollama": "http://localhost:11434",
        "groq": "https://api.groq.com/openai/v1",
        "openai": "https://api.openai.com/v1",
        "huggingface": "https://router.huggingface.co",
        "bedrock": "",
    }

    # Heavy fields stripped from finding/dependency dicts before they're sent
    # to the LLM. Keeps prompts small without losing the identifying info the
    # model needs to reason about each item.
    _DEFAULT_HEAVY_KEYS = (
        "description",
        "references",
        "cvss_v2",
        "cvss_v3",
        "code",
        "raw_xml",
        "historical_context",
        "stack_trace",
        "evidence",
    )

    # Severity ordering used by _compact when picking top-K items.
    _SEVERITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
        "unknown": 5,
        "": 6,
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        tracer: Optional[LangSmithTracer] = None,
    ):
        # Global settings
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
        # Higher ceiling for prompts that demand JSON output (vulnerability
        # fixes, deprecation summaries, etc.) so Bedrock/Claude do not truncate
        # mid-string and produce unparseable JSON. Overridable per env.
        self.json_max_tokens = int(os.getenv("LLM_JSON_MAX_TOKENS", "4096"))
        self.timeout = int(os.getenv("LLM_TIMEOUT", "120"))
        self.retry_max_attempts = int(os.getenv("LLM_RETRY_MAX_ATTEMPTS", "3"))
        self.retry_backoff_seconds = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "2.0"))

        # Prompt size budgeting — prevents 413 / context_length_exceeded errors
        # when a scan finds many issues or dependency-check returns large
        # description/reference blobs. Tunable via env without code changes.
        self.prompt_max_items = int(os.getenv("LLM_PROMPT_MAX_ITEMS", "25"))
        self.prompt_max_str_len = int(os.getenv("LLM_PROMPT_MAX_STR_LEN", "400"))
        # Conservative default (~6k tokens). Groq free tier often rejects bodies
        # well below the model's nominal context window, so keep this low.
        self.prompt_max_chars = int(os.getenv("LLM_PROMPT_MAX_CHARS", "24000"))
        # Per-file budget when embedding source/test content into a prompt
        # (used by pr_agent's nondeterministic remediation + test generation).
        # Keeps one large file from blowing the whole prompt budget.
        self.prompt_file_max_chars = int(os.getenv("LLM_PROMPT_FILE_MAX_CHARS", "12000"))
        # Optional LangChain path (mainly for OpenAI-compatible providers)
        self.use_langchain = os.getenv("LLM_USE_LANGCHAIN", "false").lower() in (
            "1", "true", "yes", "on"
        )
        self.tracer = tracer or LangSmithTracer()

        self.provider = provider or os.getenv("LLM_PROVIDER", LLMProvider.OLLAMA.value)

        if self.provider == LLMProvider.OLLAMA.value:
            self.model = model or os.getenv("OLLAMA_MODEL", self._DEFAULT_MODELS["ollama"])
            self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", self._DEFAULT_URLS["ollama"])
            self.api_key = None
            self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
            self._available = self._check_ollama_available()

        elif self.provider == LLMProvider.GROQ.value:
            self.model = model or os.getenv("GROQ_MODEL", self._DEFAULT_MODELS["groq"])
            self.base_url = base_url or os.getenv("GROQ_BASE_URL", self._DEFAULT_URLS["groq"])
            self.api_key = api_key or os.getenv("GROQ_API_KEY")
            self._available = self.api_key is not None

        elif self.provider == LLMProvider.OPENAI.value:
            self.model = model or os.getenv("OPENAI_MODEL", self._DEFAULT_MODELS["openai"])
            self.base_url = base_url or os.getenv("OPENAI_BASE_URL", self._DEFAULT_URLS["openai"])
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self._available = self.api_key is not None

        elif self.provider == LLMProvider.HUGGINGFACE.value:
            self.model = model or os.getenv("HF_MODEL", self._DEFAULT_MODELS["huggingface"])
            self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY")
            self.base_url = base_url or os.getenv("HF_BASE_URL", self._DEFAULT_URLS["huggingface"])
            self._available = self.api_key is not None

        elif self.provider == LLMProvider.BEDROCK.value:
            self.model = model or os.getenv("BEDROCK_MODEL_ID", self._DEFAULT_MODELS["bedrock"])
            self.region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-2"
            self.bedrock_inference_profile_arn = os.getenv("BEDROCK_INFERENCE_PROFILE_ARN")
            self.api_key = None
            self.base_url = ""
            self._available = self._check_bedrock_available()

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def _check_bedrock_available(self) -> bool:
        """
        Check whether AWS credentials and Bedrock runtime access are available.
        """
        try:
            sts_client = boto3.client("sts", region_name=self.region)
            sts_client.get_caller_identity()
            # Build runtime client lazily and validate credentials/model access with converse.
            self._bedrock_client = boto3.client("bedrock-runtime", region_name=self.region)
            return True
        except Exception as e:
            print(f"Bedrock is not available: {e}")
            return False

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is reachable and the configured model exists."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if response.status_code != 200:
                return False
            models = [m.get("name", "") for m in response.json().get("models", [])]
            if self.model not in models:
                base = self.model.split(":")[0]
                if not any(base in m for m in models):
                    print(f"Ollama model '{self.model}' not found. Available: {models}")
                    return False
            return True
        except Exception:
            return False

    def warmup(self) -> bool:
        """
        Pre-load the model into memory so the first real call is fast.
        Only needed for Ollama (local); cloud providers are always warm.
        Returns True if the model responded.
        """
        if self.provider != LLMProvider.OLLAMA.value or not self._available:
            return False
        try:
            print(f"  Warming up {self.model} (loading into RAM)...", flush=True)
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "hi",
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1, "num_ctx": self.num_ctx},
                },
                timeout=180,
            )
            if response.status_code == 200:
                print(f"  Model {self.model} ready.", flush=True)
                return True
            else:
                print(f"  Warmup failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"  Warmup failed: {e}")
            return False

    def is_available(self) -> bool:
        """Check if LLM service is available."""
        return self._available

    def get_config(self) -> Dict[str, Any]:
        """Return the active LLM configuration (useful for debugging)."""
        config = {
            "provider": self.provider,
            "model": self.model,
            "available": self._available,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "use_langchain": self.use_langchain,
            "langsmith_enabled": self.tracer.is_enabled(),
        }
        if self.provider == LLMProvider.OLLAMA.value:
            config["num_ctx"] = self.num_ctx
            config["base_url"] = self.base_url
        if self.provider == LLMProvider.BEDROCK.value:
            config["region"] = self.region
            config["inference_profile_arn"] = self.bedrock_inference_profile_arn
        return config

    # ------------------------------------------------------------------
    # Prompt budgeting helpers
    # ------------------------------------------------------------------

    def _compact(
        self,
        items: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        drop_keys: Optional[List[str]] = None,
        max_str_len: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Shrink a list of finding/dependency dicts so it fits in an LLM prompt.

        - Sorts by severity (critical first) so the top-K kept items are the
          most important.
        - Drops heavy keys that explode prompt size without adding signal
          (full CVE descriptions, reference link arrays, raw XML, etc.).
        - Truncates remaining string fields to max_str_len characters so a
          single huge field can't blow the budget on its own.

        This is a deterministic, lossy compression. For full data, the raw
        results stay in scan_result["raw_results"]; only the LLM prompt is
        compacted.
        """
        if not isinstance(items, list) or not items:
            return []

        top_k = top_k if top_k is not None else self.prompt_max_items
        max_str_len = max_str_len if max_str_len is not None else self.prompt_max_str_len
        drop_keys = list(drop_keys) if drop_keys is not None else list(self._DEFAULT_HEAVY_KEYS)

        def _sev_rank(item: Dict[str, Any]) -> int:
            sev = (item.get("severity") or "").lower()
            return self._SEVERITY_ORDER.get(sev, self._SEVERITY_ORDER[""])

        ordered = sorted(items, key=_sev_rank)
        if top_k > 0:
            ordered = ordered[:top_k]

        compacted: List[Dict[str, Any]] = []
        for item in ordered:
            if not isinstance(item, dict):
                # Last-resort: stringify and truncate non-dict entries.
                compacted.append({"value": str(item)[:max_str_len]})
                continue
            slim: Dict[str, Any] = {}
            for k, v in item.items():
                if k in drop_keys:
                    continue
                if isinstance(v, str) and len(v) > max_str_len:
                    slim[k] = v[:max_str_len] + "…(truncated)"
                else:
                    slim[k] = v
            compacted.append(slim)
        return compacted

    @staticmethod
    def _is_context_length_error(response) -> bool:
        """
        Detect provider-specific context-length / payload-size error codes
        beyond a bare HTTP 413, e.g. OpenAI's `context_length_exceeded` or
        Groq's `request_too_large`.
        """
        if response is None:
            return False
        try:
            body = response.json()
        except Exception:
            return False
        err = (body or {}).get("error") or {}
        code = (err.get("code") or err.get("type") or "").lower()
        msg = (err.get("message") or "").lower()
        markers = (
            "context_length_exceeded",
            "request_too_large",
            "rate_limit_exceeded_tokens",
            "string_above_max_length",
            "too large",
            "payload",
        )
        return any(m in code or m in msg for m in markers)

    @staticmethod
    def _approx_token_count(text: str) -> int:
        """
        Rough token estimate. Uses tiktoken when available for accuracy,
        otherwise falls back to chars/4 which is the standard heuristic.
        """
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, len(text) // 4)

    def truncate_code_blob(self, text: str, max_chars: Optional[int] = None) -> str:
        """
        Bound a single code blob (source file, test file, etc.) before embedding
        it in a prompt.

        Keeps the head and the tail of the file (where imports, class headers,
        and closing braces live) and replaces the middle with a marker. This
        preserves more useful context for code than blunt tail truncation.
        """
        if not isinstance(text, str):
            text = str(text)
        max_chars = max_chars if max_chars is not None else self.prompt_file_max_chars
        if max_chars <= 0 or len(text) <= max_chars:
            return text

        marker = "\n\n…(file truncated to fit prompt budget)…\n\n"
        keep = max_chars - len(marker)
        if keep <= 0:
            return text[:max_chars]
        head = keep // 2
        tail = keep - head
        return text[:head] + marker + text[-tail:]

    def _fit_prompt(
        self,
        prompt_builder,
        items: List[Dict[str, Any]],
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Repeatedly compact `items` until the rendered prompt fits in
        max_chars. Halves top_k first, then max_str_len, before giving up.

        prompt_builder is a callable(items_list) -> str that returns the
        full prompt string. This keeps the surrounding template fixed and
        only varies the part that actually grows with input size.
        """
        max_chars = max_chars if max_chars is not None else self.prompt_max_chars

        top_k = self.prompt_max_items
        max_str_len = self.prompt_max_str_len

        for _ in range(8):
            compacted = self._compact(items, top_k=top_k, max_str_len=max_str_len)
            prompt = prompt_builder(compacted)
            if len(prompt) <= max_chars:
                return prompt
            if top_k > 5:
                top_k = max(5, top_k // 2)
            elif max_str_len > 80:
                max_str_len = max(80, max_str_len // 2)
            else:
                break

        # Last resort: keep only counts + first 5 items at minimum truncation.
        compacted = self._compact(items, top_k=5, max_str_len=80)
        prompt = prompt_builder(compacted)
        if len(prompt) > max_chars:
            prompt = prompt[: max_chars - 64] + "\n…(prompt truncated to fit budget)"
        return prompt

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text using Ollama."""
        # Combine system prompt and user prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        effective_max_tokens = max_tokens or self.max_tokens

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "num_predict": effective_max_tokens,
            }
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Ollama request timed out ({self.timeout}s). "
                f"The model is running on CPU and may need more time. "
                f"Increase LLM_TIMEOUT in .env or use a smaller model."
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API request failed: {str(e)}")

    def _generate_openai_compat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text using any OpenAI-compatible chat completions API.
        Works with: OpenAI, Groq, Together AI, OpenRouter, etc.
        Uses raw HTTP requests — no openai package required.
        """
        effective_max_tokens = max_tokens or self.max_tokens

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": effective_max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        attempts = max(1, self.retry_max_attempts)
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )

                # Handle provider rate limits with retry/backoff.
                if response.status_code == 429:
                    if attempt >= attempts:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait_s = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        wait_s = 0.0
                    if wait_s <= 0:
                        wait_s = self.retry_backoff_seconds * attempt
                    print(
                        f"{self.provider} rate limited (429). "
                        f"Retrying in {wait_s:.1f}s (attempt {attempt}/{attempts})"
                    )
                    time.sleep(min(wait_s, 30.0))
                    continue

                # Retry transient server-side failures.
                if 500 <= response.status_code < 600 and attempt < attempts:
                    wait_s = self.retry_backoff_seconds * attempt
                    print(
                        f"{self.provider} server error ({response.status_code}). "
                        f"Retrying in {wait_s:.1f}s (attempt {attempt}/{attempts})"
                    )
                    time.sleep(min(wait_s, 30.0))
                    continue

                # Payload too large / context length exceeded — shrink the user
                # message and retry once. We keep the system prompt intact and
                # truncate the user content from the head so the closing
                # instructions (which usually appear at the end of templates)
                # are preserved.
                if response.status_code == 413 or self._is_context_length_error(response):
                    user_msg = next(
                        (m for m in payload["messages"] if m.get("role") == "user"),
                        None,
                    )
                    if user_msg and not payload.get("_shrunk_once"):
                        original_len = len(user_msg.get("content", ""))
                        target_len = max(1024, original_len // 2)
                        user_msg["content"] = (
                            user_msg["content"][-target_len:]
                            if original_len > target_len
                            else user_msg["content"]
                        )
                        payload["_shrunk_once"] = True
                        # Strip our internal sentinel before sending again —
                        # OpenAI-compat servers reject unknown top-level keys.
                        retry_payload = {k: v for k, v in payload.items() if not k.startswith("_")}
                        print(
                            f"{self.provider} returned {response.status_code} "
                            f"(payload too large). Retrying once with prompt "
                            f"shrunk from {original_len} to {len(user_msg['content'])} chars."
                        )
                        try:
                            response = requests.post(
                                f"{self.base_url}/chat/completions",
                                headers=headers,
                                json=retry_payload,
                                timeout=self.timeout,
                            )
                            if response.ok:
                                result = response.json()
                                return result["choices"][0]["message"]["content"].strip()
                        except requests.exceptions.RequestException:
                            pass
                    raise RuntimeError(
                        f"{self.provider} rejected the request as too large "
                        f"({response.status_code}). Reduce LLM_PROMPT_MAX_ITEMS, "
                        f"LLM_PROMPT_MAX_STR_LEN, or LLM_PROMPT_MAX_CHARS, or "
                        f"switch to a model with a larger context window."
                    )

                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()

            except requests.exceptions.Timeout:
                if attempt < attempts:
                    wait_s = self.retry_backoff_seconds * attempt
                    print(
                        f"{self.provider} timeout ({self.timeout}s). "
                        f"Retrying in {wait_s:.1f}s (attempt {attempt}/{attempts})"
                    )
                    time.sleep(min(wait_s, 30.0))
                    continue
                raise RuntimeError(f"{self.provider} request timed out ({self.timeout}s)")
            except requests.exceptions.RequestException as e:
                if attempt < attempts:
                    wait_s = self.retry_backoff_seconds * attempt
                    print(
                        f"{self.provider} request failed. "
                        f"Retrying in {wait_s:.1f}s (attempt {attempt}/{attempts}): {e}"
                    )
                    time.sleep(min(wait_s, 30.0))
                    continue
                raise RuntimeError(f"{self.provider} API request failed: {str(e)}")

        raise RuntimeError(f"{self.provider} API request failed after retries")

    def _generate_openai_compat_langchain(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text via LangChain ChatOpenAI for OpenAI-compatible providers.
        Works well with Groq/OpenAI base URLs.
        """
        effective_max_tokens = max_tokens or self.max_tokens
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
        except Exception as e:
            raise RuntimeError(f"LangChain imports failed: {e}")

        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
            max_tokens=effective_max_tokens,
            timeout=self.timeout,
        )

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        response = llm.invoke(messages)
        content = response.content
        if isinstance(content, str):
            return content.strip()
        # LangChain may return list/blocks for some providers
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", item)))
                else:
                    parts.append(str(item))
            return "\n".join(parts).strip()
        return str(content).strip()

    def _generate_huggingface(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using Hugging Face Inference API (router.huggingface.co)."""
        effective_max_tokens = max_tokens or self.max_tokens

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": effective_max_tokens,
            "temperature": temperature,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            response = requests.post(
                f"{self.base_url}/hf-inference/models/{self.model}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            raise RuntimeError(f"HuggingFace request timed out ({self.timeout}s)")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"HuggingFace API request failed: {str(e)}")

    def _generate_bedrock(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text using AWS Bedrock Runtime converse API.
        """
        effective_max_tokens = max_tokens or self.max_tokens
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        system = [{"text": system_prompt}] if system_prompt else []

        converse_kwargs: Dict[str, Any] = {
            "modelId": self.model,
            "messages": messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": effective_max_tokens,
            },
        }
        if system:
            converse_kwargs["system"] = system
        if self.bedrock_inference_profile_arn:
            converse_kwargs["inferenceProfileArn"] = self.bedrock_inference_profile_arn

        attempts = max(1, self.retry_max_attempts)
        for attempt in range(1, attempts + 1):
            try:
                response = self._bedrock_client.converse(**converse_kwargs)
                output = response.get("output", {})
                message = output.get("message", {})
                content_blocks = message.get("content", [])
                text_parts: List[str] = []
                for block in content_blocks:
                    text = block.get("text")
                    if text:
                        text_parts.append(text)
                result = "\n".join(text_parts).strip()
                if not result:
                    raise RuntimeError("Bedrock returned an empty response.")
                return result
            except ClientError as e:
                err_code = (e.response.get("Error", {}) or {}).get("Code", "Unknown")
                retryable = err_code in {
                    "ThrottlingException",
                    "TooManyRequestsException",
                    "ServiceUnavailableException",
                    "InternalServerException",
                    "ModelTimeoutException",
                }
                if retryable and attempt < attempts:
                    wait_s = self.retry_backoff_seconds * attempt
                    print(
                        f"bedrock client error ({err_code}). "
                        f"Retrying in {wait_s:.1f}s (attempt {attempt}/{attempts})"
                    )
                    time.sleep(min(wait_s, 30.0))
                    continue
                raise RuntimeError(f"Bedrock API request failed ({err_code}): {e}")
            except BotoCoreError as e:
                if attempt < attempts:
                    wait_s = self.retry_backoff_seconds * attempt
                    print(
                        f"bedrock transport error. "
                        f"Retrying in {wait_s:.1f}s (attempt {attempt}/{attempts}): {e}"
                    )
                    time.sleep(min(wait_s, 30.0))
                    continue
                raise RuntimeError(f"Bedrock transport failed: {e}")

    def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate text using the configured LLM provider.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        
        Returns:
            Generated text
        """
        if not self.is_available():
            raise RuntimeError(
                f"LLM service is not available. "
                f"Provider: {self.provider}. "
                f"Please check your configuration."
            )

        # Defensive top-level guard. Some callers build their own prompts
        # (pr_agent embeds whole source files, etc.) and don't go through
        # the per-helper budgeting in _fit_prompt. If the rendered prompt
        # exceeds prompt_max_chars, tail-preserve it: the closing instruction
        # block in our prompt templates lives at the end and matters most
        # for steering the model. This catches every caller — present and
        # future — before the request hits the provider.
        if isinstance(prompt, str) and len(prompt) > self.prompt_max_chars:
            original_chars = len(prompt)
            marker = "…(prompt head truncated to fit LLM_PROMPT_MAX_CHARS budget)\n"
            keep = max(1, self.prompt_max_chars - len(marker))
            prompt = marker + prompt[-keep:]
            print(
                f"LLMService.generate: prompt {original_chars} chars exceeded "
                f"LLM_PROMPT_MAX_CHARS={self.prompt_max_chars}; tail-preserved "
                f"to {len(prompt)} chars."
            )

        io_trace = getattr(self.tracer, "record_component_io", None)
        if callable(io_trace):
            io_trace(
                name="llm.generate.io",
                component_input={
                    "provider": self.provider,
                    "model": self.model,
                    "prompt": prompt,
                    "system_prompt": system_prompt or "",
                    "temperature": temperature,
                    "max_tokens": max_tokens or self.max_tokens,
                    "use_langchain": self.use_langchain,
                },
                component_output={"status": "started"},
                metadata={"component": "LLMService"},
                tags=["llm", "input"],
            )

        with self.tracer.trace(
            name="llm.generate",
            inputs={
                "provider": self.provider,
                "model": self.model,
                "prompt_chars": len(prompt),
                "has_system_prompt": bool(system_prompt),
                "temperature": temperature,
                "max_tokens": max_tokens or self.max_tokens,
            },
            metadata={"component": "LLMService"},
            tags=["llm", self.provider],
        ) as trace_run:
            output_text = ""
            if self.provider == LLMProvider.OLLAMA.value:
                output_text = self._generate_ollama(prompt, system_prompt, temperature, max_tokens)
            elif self.provider in (LLMProvider.OPENAI.value, LLMProvider.GROQ.value):
                if self.use_langchain:
                    try:
                        output_text = self._generate_openai_compat_langchain(
                            prompt, system_prompt, temperature, max_tokens
                        )
                        if callable(io_trace):
                            io_trace(
                                name="llm.generate.output",
                                component_input={"provider": self.provider, "path": "langchain"},
                                component_output={
                                    "response": output_text,
                                    "response_chars": len(output_text),
                                },
                                metadata={"component": "LLMService"},
                                tags=["llm", "output"],
                            )
                        if trace_run is not None:
                            try:
                                trace_run.add_outputs(
                                    {
                                        "provider": self.provider,
                                        "path": "langchain",
                                        "response": output_text,
                                        "response_chars": len(output_text),
                                    }
                                )
                            except Exception:
                                pass
                        return output_text
                    except Exception as e:
                        # Fail open to existing stable path.
                        print(f"LangChain path failed, falling back to direct HTTP: {e}")
                output_text = self._generate_openai_compat(prompt, system_prompt, temperature, max_tokens)
            elif self.provider == LLMProvider.HUGGINGFACE.value:
                output_text = self._generate_huggingface(prompt, system_prompt, temperature, max_tokens)
            elif self.provider == LLMProvider.BEDROCK.value:
                output_text = self._generate_bedrock(prompt, system_prompt, temperature, max_tokens)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            if callable(io_trace):
                io_trace(
                    name="llm.generate.output",
                    component_input={"provider": self.provider, "path": "direct"},
                    component_output={
                        "response": output_text,
                        "response_chars": len(output_text),
                    },
                    metadata={"component": "LLMService"},
                    tags=["llm", "output"],
                )
            if trace_run is not None:
                try:
                    trace_run.add_outputs(
                        {
                            "provider": self.provider,
                            "path": "direct",
                            "response": output_text,
                            "response_chars": len(output_text),
                        }
                    )
                except Exception:
                    pass
            return output_text

    def generate_release_notes(
        self, 
        changes: List[Dict], 
        issues: List[Dict],
        project_context: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate human-readable release notes from changes and issues.
        
        Args:
            changes: List of code changes
            issues: List of issues found
            project_context: Additional project context
            max_tokens: Maximum tokens to generate (optional, uses model default if None)
        
        Returns:
            Formatted release notes
        """
        # Strip heavy fields from project_context once; the changes/issues
        # lists go through _fit_prompt which budgets them dynamically.
        slim_ctx = {
            k: v
            for k, v in (project_context or {}).items()
            if k not in ("historical_context", "build_result", "repo_info")
        }

        def _build(compacted_items: List[Dict[str, Any]]) -> str:
            half = max(1, len(compacted_items) // 2)
            compacted_changes = compacted_items[:half]
            compacted_issues = compacted_items[half:]
            return f"""Generate professional release notes based on the following information:

Code Changes (top by severity, heavy fields stripped):
{json.dumps(compacted_changes, indent=2, default=str)}

Issues Found (top by severity, heavy fields stripped):
{json.dumps(compacted_issues, indent=2, default=str)}

Project Context:
{json.dumps(slim_ctx, indent=2, default=str)}

Create well-structured release notes with:
1. Summary of changes
2. Security updates (if any)
3. Bug fixes
4. New features
5. Breaking changes (if any)
6. Upgrade notes

Format as markdown."""

        merged = list(changes or []) + list(issues or [])
        prompt = self._fit_prompt(_build, merged)

        system_prompt = "You are a technical writer specializing in software release notes. Create clear, professional, and informative release notes."

        return self.generate(prompt=prompt, system_prompt=system_prompt, max_tokens=max_tokens)

    def suggest_vulnerability_fixes(
        self,
        vulnerabilities: List[Dict],
        max_tokens: Optional[int] = None,
        historical_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """
        Suggest fixes for security vulnerabilities.

        Args:
            vulnerabilities: List of vulnerability issues.
            max_tokens: Maximum tokens to generate (optional).
            historical_context: Optional compact RAG summary of past scans
                of this project. When provided, the prompt asks the model
                to ground recommendations in recurring issue patterns.

        Returns:
            List of suggestions with fixes.
        """
        history_block = ""
        if historical_context:
            history_block = (
                "\n\nHistorical context (summary of past scans of this "
                "project, retrieved via RAG; use to spot recurring issue "
                "types and recommend durable fixes when appropriate):\n"
                f"{json.dumps(historical_context, indent=2, default=str)}\n"
            )

        def _build(compacted: List[Dict[str, Any]]) -> str:
            return f"""Analyze the following security vulnerabilities and suggest specific fixes.

The list has been pre-filtered to the highest-severity findings and heavy
fields (full CVE descriptions, references, raw CVSS objects) have been
stripped to keep the prompt size bounded.

Vulnerabilities:
{json.dumps(compacted, indent=2, default=str)}{history_block}

For each vulnerability, provide:
1. A clear explanation of the issue
2. Specific code fix suggestions
3. Best practices to prevent similar issues
4. Priority level (critical, high, medium, low)
5. If the vulnerability matches a recurring issue type from historical
   context, set `"recurring": true` and briefly note the pattern in the
   explanation; otherwise omit the field.

Respond with a single valid RFC 8259 JSON array of suggestion objects.

Strict JSON rules:
- Use double quotes for all keys and string values.
- Escape any double quote inside a string value as \\".
- Do not use trailing commas.
- Do not wrap the JSON in markdown fences or add commentary before or after."""

        prompt = self._fit_prompt(_build, vulnerabilities or [])

        system_prompt = (
            "You are a security expert. Provide actionable, specific fixes for "
            "security vulnerabilities. Respond ONLY with a valid JSON array. "
            "Escape any inner double quotes as \\\"."
        )

        effective_max_tokens = max_tokens or max(self.max_tokens, self.json_max_tokens)
        try:
            response = self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=effective_max_tokens,
            )
            suggestions = extract_json_from_llm(
                response, expect="array", log_label="suggest_vulnerability_fixes"
            )
            if isinstance(suggestions, list):
                return suggestions
            if isinstance(suggestions, dict):
                for key in ("suggestions", "fixes", "items", "data"):
                    value = suggestions.get(key)
                    if isinstance(value, list):
                        return value
            return []
        except Exception as e:
            print(f"Failed to parse vulnerability suggestions: {e}")
            return []

    def summarize_deprecation_issues(
        self, 
        deprecation_issues: List[Dict],
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Summarize deprecated code issues with recommendations.
        
        Args:
            deprecation_issues: List of deprecation issues
            max_tokens: Maximum tokens to generate (optional, uses model default if None)
        
        Returns:
            Summary with recommendations
        """
        def _build(compacted: List[Dict[str, Any]]) -> str:
            return f"""Analyze the following deprecation issues and provide a comprehensive summary.

The list has been pre-filtered to the highest-severity findings and heavy
fields have been stripped to keep the prompt size bounded.

Deprecation Issues:
{json.dumps(compacted, indent=2, default=str)}

Provide:
1. Summary of deprecated patterns found
2. Impact assessment
3. Migration recommendations
4. Priority for addressing each issue
5. Estimated effort for fixes

Respond with a single valid RFC 8259 JSON object.

Strict JSON rules:
- Use double quotes for all keys and string values.
- Escape any double quote inside a string value as \\".
- Do not use trailing commas.
- Do not wrap the JSON in markdown fences or add commentary before or after."""

        prompt = self._fit_prompt(_build, deprecation_issues or [])

        system_prompt = (
            "You are a code modernization expert. Help teams migrate from "
            "deprecated code patterns to modern alternatives. Respond ONLY "
            "with a valid JSON object. Escape any inner double quotes as \\\"."
        )

        effective_max_tokens = max_tokens or max(self.max_tokens, self.json_max_tokens)
        try:
            response = self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=effective_max_tokens,
            )
            summary = extract_json_from_llm(
                response, expect="object", log_label="summarize_deprecation_issues"
            )
            if isinstance(summary, dict):
                return summary
            return {
                "summary": f"Found {len(deprecation_issues)} deprecation issues",
                "recommendations": [],
            }
        except Exception as e:
            print(f"Failed to parse deprecation summary: {e}")
            return {
                "summary": f"Found {len(deprecation_issues)} deprecation issues",
                "recommendations": []
            }
