import os
import requests
from dotenv import load_dotenv

# Ensure environment variables are loaded if this module is imported directly
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

# Qwen2.5:7b is a good default — strong instruction following, runs on 8GB RAM.
# Alternatives ranked by accuracy vs speed:
#   phi3.5:3.8b   — fastest, 4GB RAM, lower quality
#   gemma2:9b     — good accuracy, 8GB RAM
#   qwen2.5:14b   — best quality, needs 16GB RAM


def ask_llm(prompt: str, temperature: float = 0.1, max_tokens: int = 2048) -> str:
    """
    Send a prompt to the locally running Ollama instance.
    temperature=0.1 keeps output deterministic for extraction tasks.
    """
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
    }

    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")
