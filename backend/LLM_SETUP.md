# LLM Setup Guide

This project supports multiple LLM providers. By default, it uses **Ollama** (open-source) for development.

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
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://localhost:11434
```

The service will work with these defaults even without a `.env` file.

## Using OpenAI (Production)

If you want to use OpenAI for production:

1. Install the OpenAI package:
```bash
pip install openai
```

2. Set environment variables:
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
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

## Model Recommendations

### For Development (Ollama):
- **llama3.2:3b** - Fast, small, good for testing
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
