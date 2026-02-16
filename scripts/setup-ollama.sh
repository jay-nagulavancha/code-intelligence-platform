#!/bin/bash
# =============================================================================
# Setup script to pull the Ollama model after container startup
# Usage: ./scripts/setup-ollama.sh [model_name]
# =============================================================================

set -e

MODEL="${1:-llama3.2:3b}"
OLLAMA_HOST="${OLLAMA_HOST:-localhost}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_URL="http://${OLLAMA_HOST}:${OLLAMA_PORT}"

echo "================================================"
echo "  Code Intelligence Platform - Ollama Setup"
echo "================================================"
echo ""
echo "  Ollama URL: ${OLLAMA_URL}"
echo "  Model:      ${MODEL}"
echo ""

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while ! curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "❌ Ollama is not responding after ${MAX_RETRIES} attempts."
        echo "   Make sure Ollama is running: docker compose up -d ollama"
        exit 1
    fi
    echo "   Attempt ${RETRY_COUNT}/${MAX_RETRIES}..."
    sleep 2
done

echo "✅ Ollama is ready!"
echo ""

# Check if model is already downloaded
echo "🔍 Checking if model '${MODEL}' is available..."
if curl -sf "${OLLAMA_URL}/api/tags" | grep -q "\"${MODEL}\""; then
    echo "✅ Model '${MODEL}' is already available."
else
    echo "📥 Pulling model '${MODEL}'... (this may take several minutes)"
    echo ""
    docker compose exec ollama ollama pull "${MODEL}"
    echo ""
    echo "✅ Model '${MODEL}' pulled successfully!"
fi

echo ""
echo "================================================"
echo "  Setup complete! Available models:"
echo "================================================"
curl -sf "${OLLAMA_URL}/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for model in data.get('models', []):
    name = model.get('name', 'unknown')
    size = model.get('size', 0) / (1024**3)
    print(f'  - {name} ({size:.1f} GB)')
" 2>/dev/null || echo "  (Could not list models)"

echo ""
echo "🚀 Ready! Test with:"
echo "   curl http://localhost:8000/health"
echo ""
