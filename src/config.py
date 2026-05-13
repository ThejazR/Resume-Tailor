"""Central config loaded from env. Import once, use everywhere."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "resume"
EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi4-mini")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp-mail.outlook.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "")

RESUME_PDF = PROJECT_ROOT / "resume.pdf"
OUT_DIR = PROJECT_ROOT / "out"
