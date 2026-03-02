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
