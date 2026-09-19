"""
Namesniper - Configuration Module
"""
import sys
import os
import json
import shutil
from pathlib import Path

VERSION = "1.2.0"

if getattr(sys, "frozen", False):
    RESOURCE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).resolve().parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    APP_DIR = RESOURCE_DIR

BASE_DIR = APP_DIR
WORDLISTS_DIR = APP_DIR / "wordlists"
EXPORTS_DIR = APP_DIR / "exports"
CONFIG_FILE = APP_DIR / "config.json"
DATABASE_FILE = APP_DIR / "namesniper.db"
STEAM_DATABASE_FILE = APP_DIR / "steam_names.db"

# Ensure runtime directories exist
WORDLISTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

def get_wordlist_path(filename: str) -> Path:
    """Resolve wordlist path from local folder or fallback to bundled resources."""
    local_path = WORDLISTS_DIR / filename
    if local_path.exists():
        return local_path
    bundled_path = RESOURCE_DIR / "wordlists" / filename
    if bundled_path.exists():
        return bundled_path
    return local_path

def ensure_default_wordlists() -> None:
    """Populate local wordlists directory from bundled assets if missing."""
    bundled_dir = RESOURCE_DIR / "wordlists"
    if bundled_dir.exists() and bundled_dir != WORDLISTS_DIR:
        for item in bundled_dir.glob("*.txt"):
            target = WORDLISTS_DIR / item.name
            if not target.exists():
                try:
                    shutil.copy2(item, target)
                except Exception:
                    pass

ensure_default_wordlists()

DEFAULT_CONFIG = {
    "api_keys": [],  # List of Faceit API keys for round-robin rotation
    "active_key": "",
    "threads": 3,  # Safe concurrency for Faceit API rate limits
    "delay_between_requests": 0.35,  # Delay in seconds per worker to avoid 429
    "save_taken": False,
    "filter_min_length": 3,
    "filter_max_length": 12,
    "detect_idle_accounts": True,
    "skip_already_checked": True,
    "proxies": [],
    "proxy_enabled": False,
    "export_format": "txt",  # txt or csv
    "steam_api_key": ""
}

def load_config() -> dict:
    """Load configuration from config.json or return defaults."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config: dict) -> None:
    """Persist configuration to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")
