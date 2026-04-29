# LLM Setup Guide

This project supports multiple LLM providers. By default, it uses **Ollama** (open-source) for development.
It can also trace scan/LLM runs to **LangSmith** for observability.

## Quick Start with Ollama (Recommended for Development)

### 1. Install Ollama

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download from [https://ollama.com/download](https://ollama.com/download)

### 2. Start Ollama Service

```bash
ollama serve
```

This starts Ollama on `http://localhost:11434` (default).

### 3. Pull a Model

For development, we recommend a smaller, faster model:

```bash
# Small model (3B parameters, ~2GB)
ollama pull llama3.2:3b

# Or medium model (7B parameters, ~4GB)
ollama pull llama3.2

# Or other options:
ollama pull mistral
ollama pull codellama
```

### 4. Configure Environment (Optional)

Create a `.env` file in the backend directory:

```bash
# Use Ollama (default)
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:1b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_NUM_CTX=8192
LLM_MAX_TOKENS=1024
LLM_TIMEOUT=120
```

The service will work with these defaults even without a `.env` file.

## Using Groq (Fast Cloud, Recommended for Demo)

1. Create a free API key at [https://console.groq.com](https://console.groq.com)

2. Set environment variables:
```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.1-8b-instant
LLM_MAX_TOKENS=1024
LLM_TIMEOUT=30
# Optional: route Groq/OpenAI calls through LangChain
LLM_USE_LANGCHAIN=true
```

## Using OpenAI (Production)

If you want to use OpenAI for production:

Set environment variables:
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_USE_LANGCHAIN=true
```

## Using Hugging Face (Optional)

1. Install dependencies:
```bash
pip install transformers torch
```

2. Set environment variables:
```bash
LLM_PROVIDER=huggingface
HUGGINGFACE_API_KEY=your_api_key_here
HF_MODEL=mistralai/Mistral-7B-Instruct-v0.2
```

## Testing LLM Connection

Check if your LLM is available:

```bash
curl http://localhost:8000/health
```

Or in Python:
```python
from app.services.llm_service import LLMService

llm = LLMService()
print(f"Available: {llm.is_available()}")
print(f"Provider: {llm.provider}")
print(f"Model: {llm.model}")
```

## LangSmith Tracing (Optional)

Enable LangSmith to trace end-to-end scan runs and LLM calls:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_your_key_here
LANGSMITH_PROJECT=code-intelligence-platform
# LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

What gets traced:
- `scan.scan_github_repo` (full GitHub scan pipeline)
- `scan.run_scan` (local pipeline orchestration)
- `llm.generate` (provider/model call metadata)

You can verify in health endpoint:

```bash
curl http://localhost:8000/health
```

Look for `langsmith_enabled: true`.

## LangChain Integration (Optional)

LangChain is integrated as an optional execution path for OpenAI-compatible providers (OpenAI/Groq).

Enable with:

```bash
LLM_USE_LANGCHAIN=true
```

Notes:
- If LangChain path fails at runtime, the service automatically falls back to direct HTTP calls.
- This keeps behavior stable while enabling LangChain-based model wrappers.

## Prompt Size Budgeting (avoiding 413 / context_length_exceeded)

Scans can produce hundreds of findings, and OWASP Dependency-Check reports can
embed very large CVE descriptions and reference link arrays. Free-tier
providers (Groq) reject oversize requests with `413 Payload Too Large`, and
self-hosted models can fail with `context_length_exceeded`. The LLM service
mitigates this with three layers — all on by default and tunable via env:

1. **Per-call compaction.** `generate_release_notes`,
   `suggest_vulnerability_fixes`, and `summarize_deprecation_issues`
   automatically:
   - sort findings by severity (critical → info),
   - keep only the top `LLM_PROMPT_MAX_ITEMS` items,
   - strip heavy keys (`description`, `references`, `cvss_v2`, `cvss_v3`,
     `code`, `raw_xml`, `historical_context`, `stack_trace`, `evidence`),
   - truncate each remaining string field to `LLM_PROMPT_MAX_STR_LEN` chars.
2. **Hard prompt-size cap.** After compaction, the rendered prompt must fit in
   `LLM_PROMPT_MAX_CHARS`. If it doesn't, the service halves `top_k` and then
   `max_str_len` until it does (or falls back to a 5-item / 80-char minimum).
3. **413 / context-length retry.** If the provider still rejects the request
   (different model, lower limit than expected), `_generate_openai_compat`
   retries once with the user message tail-truncated to half its length before
   surfacing a clear error.

### Tuning

| Variable | Default | When to change |
| --- | --- | --- |
| `LLM_PROMPT_MAX_ITEMS` | `25` | Lower (10) for Groq free tier; raise (50–100) for gpt-4o-mini / Bedrock Claude. |
| `LLM_PROMPT_MAX_STR_LEN` | `400` | Lower (200) when most findings have huge descriptions; raise (800) on high-context models. |
| `LLM_PROMPT_MAX_CHARS` | `24000` (~6k tokens) | Raise to `60000` for 32k-context models, `120000` for 128k+. |

### Optional: accurate token counting

By default, prompt size is measured in characters (≈ `chars / 4` tokens). For
exact counts, install `tiktoken`:

```bash
pip install tiktoken
```

The service will pick it up automatically when present; no config change
needed.

### What the raw scan output preserves

Compaction only affects the **prompt sent to the LLM**. The full, unmodified
scan output is still available in `scan_result["raw_results"]` and the
generated report's `raw_issues`, so downstream consumers (PR creation, RAG
storage, GitHub Issues) work on the complete data set.

## Model Recommendations

### For Development (Ollama):
- **llama3.2:1b** - Fastest on CPU, best for local scans
- **llama3.2:3b** - Better quality if your machine can handle it
- **llama3.2** - Better quality, still fast
- **mistral** - Good balance
- **codellama** - Specialized for code

### For Production (OpenAI):
- **gpt-4o-mini** - Fast and cost-effective
- **gpt-4o** - Best quality
- **gpt-3.5-turbo** - Budget option

## Troubleshooting

### Ollama not available
- Make sure Ollama is running: `ollama serve`
- Check if the model is pulled: `ollama list`
- Verify the base URL matches your Ollama instance

### Model not found
- Pull the model: `ollama pull <model_name>`
- Check available models: `ollama list`

### Slow responses
- Use a smaller model (e.g., llama3.2:3b instead of llama3.2)
- Reduce `max_tokens` in generation calls
- Consider using OpenAI for faster inference
