"""
LLM Service - Handles LLM interactions for report generation,
release notes, vulnerability suggestions, and deprecation summaries.

Supported providers:
  - ollama      : Local open-source models (default for development)
  - groq        : Free cloud inference via Groq (fastest free option)
  - openai      : OpenAI or any OpenAI-compatible API
  - huggingface : Hugging Face Inference API
"""
import os
import json
import time
import requests
from typing import Optional, Dict, Any, List
from enum import Enum
from app.services.langsmith_service import LangSmithTracer


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    GROQ = "groq"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"

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
    }

    _DEFAULT_URLS = {
        "ollama": "http://localhost:11434",
        "groq": "https://api.groq.com/openai/v1",
        "openai": "https://api.openai.com/v1",
        "huggingface": "https://router.huggingface.co",
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
        self.timeout = int(os.getenv("LLM_TIMEOUT", "120"))
        self.retry_max_attempts = int(os.getenv("LLM_RETRY_MAX_ATTEMPTS", "3"))
        self.retry_backoff_seconds = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "2.0"))
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

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

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
        return config

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
        prompt = f"""Generate professional release notes based on the following information:

Code Changes:
{json.dumps(changes, indent=2)}

Issues Found:
{json.dumps(issues, indent=2)}

Project Context:
{json.dumps(project_context or {}, indent=2)}

Create well-structured release notes with:
1. Summary of changes
2. Security updates (if any)
3. Bug fixes
4. New features
5. Breaking changes (if any)
6. Upgrade notes

Format as markdown."""

        system_prompt = "You are a technical writer specializing in software release notes. Create clear, professional, and informative release notes."

        return self.generate(prompt=prompt, system_prompt=system_prompt, max_tokens=max_tokens)

    def suggest_vulnerability_fixes(
        self, 
        vulnerabilities: List[Dict],
        max_tokens: Optional[int] = None
    ) -> List[Dict]:
        """
        Suggest fixes for security vulnerabilities.
        
        Args:
            vulnerabilities: List of vulnerability issues
            max_tokens: Maximum tokens to generate (optional, uses model default if None)
        
        Returns:
            List of suggestions with fixes
        """
        prompt = f"""Analyze the following security vulnerabilities and suggest specific fixes:

Vulnerabilities:
{json.dumps(vulnerabilities, indent=2)}

For each vulnerability, provide:
1. A clear explanation of the issue
2. Specific code fix suggestions
3. Best practices to prevent similar issues
4. Priority level (critical, high, medium, low)

Respond in JSON format with an array of suggestions."""

        system_prompt = "You are a security expert. Provide actionable, specific fixes for security vulnerabilities."

        try:
            response = self.generate(prompt=prompt, system_prompt=system_prompt, max_tokens=max_tokens)
            # Try to extract JSON from response (in case model adds extra text)
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            suggestions = json.loads(response)
            if isinstance(suggestions, list):
                return suggestions
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
        prompt = f"""Analyze the following deprecation issues and provide a comprehensive summary:

Deprecation Issues:
{json.dumps(deprecation_issues, indent=2)}

Provide:
1. Summary of deprecated patterns found
2. Impact assessment
3. Migration recommendations
4. Priority for addressing each issue
5. Estimated effort for fixes

Respond in JSON format."""

        system_prompt = "You are a code modernization expert. Help teams migrate from deprecated code patterns to modern alternatives."

        try:
            response = self.generate(prompt=prompt, system_prompt=system_prompt, max_tokens=max_tokens)
            # Try to extract JSON from response
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            summary = json.loads(response)
            return summary
        except Exception as e:
            print(f"Failed to parse deprecation summary: {e}")
            return {
                "summary": f"Found {len(deprecation_issues)} deprecation issues",
                "recommendations": []
            }
