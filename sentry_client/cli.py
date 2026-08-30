"""
cli.py — the `sentry` command. Same REPL shape as the repo's own
orchestrator_cli.py, but talking to the server over HTTP instead of
importing Orchestrator directly — this is what replaces SSH access for
teammates who don't have (and shouldn't need) a checkout of the codebase.
"""
from sentry_client.client import SentryClient


def main() -> None:
    print("SENTRY orchestrator — type an instruction, or 'exit' to quit.\n")
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

        try:
            reply = client.chat(user_input)
        except Exception as e:
            print(f"[error] {e}\n")
            continue

        print(f"\nagent> {reply}\n")


if __name__ == "__main__":
    main()
