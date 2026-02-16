"""
LLM Service - Handles LLM interactions for report generation, 
release notes, vulnerability suggestions, and deprecation summaries.
Supports multiple providers: Ollama (default), OpenAI, Hugging Face.
"""
import os
import json
import requests
from typing import Optional, Dict, Any, List
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"


class LLMService:
    """
    Service for LLM interactions. Supports multiple providers:
    - Ollama (default for development, open-source, runs locally)
    - OpenAI (for production)
    - Hugging Face (optional, for custom models)
    """

    def __init__(
        self, 
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize LLM service.
        
        Args:
            provider: LLM provider ("ollama", "openai", "huggingface")
            model: Model name (provider-specific)
            api_key: API key (for OpenAI/Hugging Face)
            base_url: Base URL for API (for Ollama/OpenAI)
        """
        # Determine provider (default to Ollama for development)
        self.provider = provider or os.getenv("LLM_PROVIDER", LLMProvider.OLLAMA.value)
        
        # Provider-specific defaults
        if self.provider == LLMProvider.OLLAMA.value:
            self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.api_key = None  # Ollama doesn't require API key
            self._available = self._check_ollama_available()
            
        elif self.provider == LLMProvider.OPENAI.value:
            self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self._available = self.api_key is not None
            
        elif self.provider == LLMProvider.HUGGINGFACE.value:
            self.model = model or os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
            self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY")
            self.base_url = base_url or os.getenv("HF_BASE_URL", "https://api-inference.huggingface.co")
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
                # Try without tag suffix (e.g. "llama3.2" matches "llama3.2:3b")
                base = self.model.split(":")[0]
                if not any(base in m for m in models):
                    print(f"Ollama model '{self.model}' not found. Available: {models}")
                    return False
            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check if LLM service is available."""
        return self._available

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

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Ollama request timed out (60s). Model may be loading or unresponsive.")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API request failed: {str(e)}")

    def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text using OpenAI API."""
        try:
            import openai
            
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return response.choices[0].message.content.strip()
        except ImportError:
            raise RuntimeError("openai package is not installed. Run: pip install openai")
        except Exception as e:
            raise RuntimeError(f"OpenAI API request failed: {str(e)}")

    def _generate_huggingface(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text using Hugging Face API."""
        # Combine system prompt and user prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "temperature": temperature,
                "return_full_text": False
            }
        }
        
        if max_tokens:
            payload["parameters"]["max_new_tokens"] = max_tokens

        try:
            response = requests.post(
                f"{self.base_url}/models/{self.model}",
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            # Handle different response formats
            if isinstance(result, list) and len(result) > 0:
                return result[0].get("generated_text", "").strip()
            elif isinstance(result, dict):
                return result.get("generated_text", "").strip()
            else:
                return str(result).strip()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Hugging Face API request failed: {str(e)}")

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

        if self.provider == LLMProvider.OLLAMA.value:
            return self._generate_ollama(prompt, system_prompt, temperature, max_tokens)
        elif self.provider == LLMProvider.OPENAI.value:
            return self._generate_openai(prompt, system_prompt, temperature, max_tokens)
        elif self.provider == LLMProvider.HUGGINGFACE.value:
            return self._generate_huggingface(prompt, system_prompt, temperature, max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

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
