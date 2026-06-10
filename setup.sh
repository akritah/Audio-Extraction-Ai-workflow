#!/bin/bash
# Run once on a fresh machine to get everything working.
# Tested on Ubuntu 22.04 and macOS 14 (Apple Silicon).

set -e

# ─────────────────────────────────────────────
# 1. Python virtual environment
# ─────────────────────────────────────────────
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r backend/requirements.txt

# spaCy model — transformer-based for best accuracy
python -m spacy download en_core_web_trf || python -m spacy download en_core_web_sm

echo ""
echo "Python deps installed."

# ─────────────────────────────────────────────
# 2. Ollama (local LLM runtime)
# ─────────────────────────────────────────────
echo ""
echo "Checking Ollama..."

if ! command -v ollama &> /dev/null; then
    echo "Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Pull the model — change to qwen2.5:14b if you have 16GB+ RAM
ollama pull qwen2.5:7b

echo "Ollama ready."

# ─────────────────────────────────────────────
# 3. Node.js / Next.js frontend
# ─────────────────────────────────────────────
echo ""
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo ""
echo "─────────────────────────────────────────"
echo "Setup complete."
echo ""
echo "Before first run, set your HuggingFace token (needed once for pyannote model download):"
echo "  export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx"
echo ""
echo "To start:"
echo "  Terminal 1 — ollama serve"
echo "  Terminal 2 — source venv/bin/activate && cd backend && python main.py"
echo "  Terminal 3 — cd frontend && npm run dev"
echo "─────────────────────────────────────────"
