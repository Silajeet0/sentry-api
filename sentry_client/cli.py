"""
cli.py — the `sentry` command. Same REPL shape as the repo's own
orchestrator_cli.py, but talking to the server over HTTP instead of
importing Orchestrator directly — this is what replaces SSH access for
teammates who don't have (and shouldn't need) a checkout of the codebase.
"""
import argparse

from sentry_client.client import SentryClient
from sentry_client.config import reset_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="sentry")
    parser.add_argument(
        "--reconnect",
        action="store_true",
        help=(
            "Clear the saved server URL/API key (~/.sentry/config.json) and "
            "re-run first-time setup before starting, instead of doing it "
            "from inside the REPL with /reconnect. Useful when scripting "
            "this, or when you'd rather not launch into a REPL that's "
            "guaranteed to fail first. See the README's Troubleshooting "
            "section for how to get the current server URL."
        ),
    )
    args = parser.parse_args()

    if args.reconnect:
        reset_config()

    print(
        "SENTRY orchestrator — type an instruction, '/reconnect' if the "
        "server URL has changed, or 'exit' to quit.\n"
    )
    client = SentryClient()

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        if user_input.lower() in {"/reconnect", "/reset-config", "/reset"}:
            # See SentryClient.reconnect's docstring — this is the fix for
            # "couldn't reach ... NameResolutionError / Failed to resolve"
            # errors, which almost always mean the server's Cloudflare
            # quick tunnel has rotated to a new hostname. Get the current
            # URL from the README's Troubleshooting section first.
            client.reconnect()
            continue

        if user_input.lower().startswith("/summary "):
            # e.g. "/summary ICML 2026" — bypasses chat() on purpose, see
            # SentryClient.get_summary's docstring.
            parts = user_input.split()
            if len(parts) != 3:
                print("usage: /summary <CONFERENCE> <YEAR>\n")
                continue
            try:
                digest = client.get_summary(parts[1], parts[2])
                print(f"\nSubject: {digest.get('subject', '(none)')}\n")
                print(digest.get("body", "(no body)"))
                print()
            except Exception as e:
                print(f"[error] {e}\n")
            continue

        if user_input.lower().startswith("/summarize "):
            # e.g. "/summarize ICML 2026" — bypasses chat()/the orchestrator
            # LLM on purpose, see SentryClient.trigger_summary's docstring.
            parts = user_input.split()
            if len(parts) != 3:
                print("usage: /summarize <CONFERENCE> <YEAR>\n")
                continue
            try:
                result = client.trigger_summary(parts[1], parts[2])
                print(f"\n{result}\n")
            except Exception as e:
                print(f"[error] {e}\n")
            continue

        try:
            reply = client.chat(user_input)
        except Exception as e:
            print(f"[error] {e}\n")
            continue

        print(f"\nagent> {reply}\n")


if __name__ == "__main__":
    main()
