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

        # Build the outgoing payload without touching self.history yet — if
        # this request fails partway (timeout, 524, connection drop), we
        # must NOT leave an orphaned, unanswered user turn sitting in
        # history: the orchestrator is stateless per-request and replays
        # whatever messages we send it, so a leftover unanswered turn gets
        # silently bundled into whatever you ask next, producing a reply
        # that answers two unrelated questions at once. Only commit both
        # the user message and the reply to self.history together, on
        # success.
        outgoing = self.history + [{"role": "user", "content": message}]

        resp = self.session.post(
            f"{self.config.base_url}/v1/chat/completions",
            json={"model": "sentry-orchestrator", "messages": outgoing},
            timeout=600,  # pipeline runs are backgrounded server-side, but
                          # tool-call round-trips inside a single turn can
                          # still take a while
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]

        self.history = outgoing + [{"role": "assistant", "content": reply}]
        return reply

    def get_summary(self, conference: str, year: str) -> dict:
        """
        Fetches an already-generated digest directly, bypassing chat()
        entirely. Use this instead of asking the orchestrator to "show me
        the summary" — that routes through another LLM generation pass and
        can 524 on a large digest (see orchestrator_api.py's
        /v1/summary/{conference}/{year} for why).
        """
        resp = self.session.get(
            f"{self.config.base_url}/v1/summary/{conference}/{year}", timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def trigger_summary(self, conference: str, year: str, refresh_cache: bool = False) -> dict:
        """
        Starts a summarize job directly, bypassing chat()/the orchestrator
        LLM entirely. Use this instead of "summarize X in the chat — the
        underlying job is always fast to *schedule*, but asking the
        orchestrator to figure that out via chat can itself be slow (cold
        Ollama model load, multi-step tool reasoning) and 524 before it
        even gets to the fast part.
        """
        resp = self.session.post(
            f"{self.config.base_url}/v1/tools/summarize/{conference}/{year}",
            params={"refresh_cache": refresh_cache},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
