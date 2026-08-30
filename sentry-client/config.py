"""
config.py — first-run setup and persistence for the sentry client's
API key + server URL, stored at ~/.sentry/config.json.

Kept deliberately dumb: no keyring/OS-credential-store integration, since
this is a 3-4 person internal tool, not a public package with a real
threat model around local file storage. If that changes, swap
_load/_save for something backed by `keyring` without touching the rest
of the client.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".sentry"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_BASE_URL = "https://sentry-api.example.org"  # replace with the real tunnel hostname


@dataclass
class SentryConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL


def load_config() -> SentryConfig:
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text())
        return SentryConfig(**data)
    return _prompt_and_save()


def _prompt_and_save() -> SentryConfig:
    print("First-time setup — this only happens once.")
    api_key = input("Enter your SENTRY API key: ").strip()
    base_url = input(f"Server URL [{DEFAULT_BASE_URL}]: ").strip() or DEFAULT_BASE_URL

    config = SentryConfig(api_key=api_key, base_url=base_url.rstrip("/"))
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2))
    CONFIG_PATH.chmod(0o600)  # key material — owner read/write only
    print(f"Saved to {CONFIG_PATH}\n")
    return config


def reset_config() -> None:
    """Delete the saved config, forcing re-prompt on next run — useful when
    a key is rotated or the server URL changes."""
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
