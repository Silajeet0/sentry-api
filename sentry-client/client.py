"""
client.py — thin wrapper around SENTRY's /v1/chat/completions.

Intentionally contains zero pipeline/scraper/extractor logic — all of that
lives server-side and can change daily without this package needing a new
release. This file should stay small forever; if it's growing, that logic
probably belongs in orchestrator/ on the server instead.
"""
from typing import Callable, List, Optional

import requests

from sentry_client.config import SentryConfig, load_config

_last_seen_commit: Optional[str] = None


class SentryClient:
    def __init__(self, config: Optional[SentryConfig] = None):
        self.config = config or load_config()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.config.api_key}"
        self.history: List[dict] = []

    def check_version(self, warn: Callable[[str], None] = print) -> None:
        """
        Best-effort drift check: compares the server's current git commit
        against the one seen on this client's previous call. Since the
        client has no logic of its own to be "out of date" against — it's
        just an HTTP+auth shim — this isn't about the client breaking, it's
        an early signal that the server restarted onto new code mid-session
        (e.g. the watcher picked up a commit), in case that's relevant to
        whatever you were in the middle of.
        """
        global _last_seen_commit
        try:
            resp = self.session.get(f"{self.config.base_url}/v1/version", timeout=5)
            resp.raise_for_status()
            commit = resp.json().get("commit")
        except requests.RequestException as e:
            warn(f"[sentry] couldn't reach {self.config.base_url}: {e}")
            return

        if _last_seen_commit and commit != _last_seen_commit:
            warn(f"[sentry] server updated ({_last_seen_commit} -> {commit}) since your last message")
        _last_seen_commit = commit

    def chat(self, message: str) -> str:
        self.check_version()
        self.history.append({"role": "user", "content": message})

        resp = self.session.post(
            f"{self.config.base_url}/v1/chat/completions",
            json={"model": "sentry-orchestrator", "messages": self.history},
            timeout=600,  # pipeline runs are backgrounded server-side, but
                          # tool-call round-trips inside a single turn can
                          # still take a while
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]

        self.history.append({"role": "assistant", "content": reply})
        return reply
