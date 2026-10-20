"""Central configuration: limits, labels and environment access (no secrets in source)."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "BusinessPilot AI"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("BP_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("BP_DB_PATH", DATA_DIR / "businesspilot.db"))

MAX_FILE_MB = int(os.getenv("BP_MAX_FILE_MB", "25"))
MAX_FILES = int(os.getenv("BP_MAX_FILES", "10"))
MAX_ROWS = int(os.getenv("BP_MAX_ROWS", "500000"))
MAX_PDF_PAGES = int(os.getenv("BP_MAX_PDF_PAGES", "60"))

SUPPORTED_EXTENSIONS = ["csv", "xlsx", "xls", "json", "txt", "pdf", "docx", "doc",
                        "png", "jpg", "jpeg", "webp"]

# Magic-byte signatures used to confirm that a file really is what its extension claims.
SIGNATURES = {
    "pdf": [b"%PDF"],
    "xlsx": [b"PK\x03\x04"],
    "docx": [b"PK\x03\x04"],
    "xls": [b"\xd0\xcf\x11\xe0"],
    "doc": [b"\xd0\xcf\x11\xe0"],
    "png": [b"\x89PNG"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "webp": [b"RIFF"],
}

REPORT_TYPES = [
    "Executive Business Report", "Financial Performance Report", "Sales Analysis Report",
    "Profit and Loss Report", "Business Growth Report", "Customer Analysis Report",
    "Marketing Performance Report", "Inventory Analysis Report",
    "Forecast and Risk Report", "General Data Analysis Report",
]


def openai_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return key or None


def openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
