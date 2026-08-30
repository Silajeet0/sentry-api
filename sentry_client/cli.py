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

        try:
            reply = client.chat(user_input)
        except Exception as e:
            print(f"[error] {e}\n")
            continue

        print(f"\nagent> {reply}\n")


if __name__ == "__main__":
    main()
