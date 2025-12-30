# LLM_Server/serve/config.py
import os
from pathlib import Path

# Stable defaults; override via env vars if needed
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../FuzzyBot_HSBI
MODELS_DIR = Path(os.environ.get("FUZZYBOT_MODELS_DIR", str(PROJECT_ROOT / "Models"))).expanduser()

DEFAULT_MODEL_NAME = os.environ.get("FUZZYBOT_MODEL_NAME", "Apertus-8B-Instruct-2509")
MODEL_DIR = MODELS_DIR / DEFAULT_MODEL_NAME

HOST = os.environ.get("FUZZYBOT_HOST", "0.0.0.0")
PORT = int(os.environ.get("FUZZYBOT_PORT", "9000"))

RAG_DB_DIR = Path(os.environ.get("FUZZYBOT_RAG_DB_DIR", str(PROJECT_ROOT / "LLM_Server" / "rag" / "db"))).expanduser()
