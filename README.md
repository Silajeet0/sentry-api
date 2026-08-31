# sentry-api

A thin command-line client for the SENTRY orchestrator API. Lets you drive
SENTRY — trigger extraction runs, check status, generate and read summaries,
kick off IKDD RPA submissions — from any machine, without SSH access to the
Mac SENTRY actually runs on.

**Important:** this package contains no pipeline logic of its own. It's an
HTTP client, nothing more — every extraction, scrape, summarization, and RPA
submission happens on the server (the Mac), and all resulting data is saved
there, under `data/final_output/` in the SENTRY repo. Running `sentry` from
your laptop does not download or store any of that data locally — replies
are printed to your terminal and nothing else. If you want your own local
copy of something (e.g. a digest), redirect the output yourself.

---

## 1. First-time setup

### Prerequisites
- Python 3.9+
- Either `pipx` (recommended) or a plain virtual environment

### Install

**Recommended — pipx** (isolates the install, but `sentry` still works as a
normal global command, no activation needed):

```bash
brew install pipx        # macOS; see pipx docs for other platforms
pipx install git+https://github.com/Silajeet0/sentry-api.git
```

**Alternative — plain venv:**

```bash
python3 -m venv ~/.sentry-api-venv
source ~/.sentry-api-venv/bin/activate
pip install git+https://github.com/Silajeet0/sentry-api.git
```

If you use the venv route, remember you need to `source
~/.sentry-api-venv/bin/activate` in every new terminal session before
`sentry` will be found.

### Initialize

Run it once:

```bash
sentry
```

On first run, since no config exists yet, you'll be prompted:

```
First-time setup — this only happens once.
Enter your SENTRY API key: <paste the key you were given>
Server URL [https://sentry-api.example.org]: <paste the current tunnel URL>
```

This gets saved to `~/.sentry/config.json` (permissions locked to
owner-read/write only) and you won't be asked again — every future `sentry`
invocation reuses it automatically.

**Where to get your API key and server URL:** ask whoever's running the Mac
server. The server URL in particular *can change* — see the Quick Tunnel
note in section 4.

---

## 2. Using it

Run `sentry` to start an interactive session:

```
❯ sentry
SENTRY orchestrator — type an instruction, or 'exit' to quit.
you> is the data for ICLR 2025 available?
agent> ...
you> exit
```

Type `exit` or `quit` (or Ctrl-D / Ctrl-C) to leave.

### Plain chat

Anything you type that isn't one of the slash commands below goes straight
to the orchestrator as a natural-language instruction — trigger a run,
check status, ask what's on disk, ask it to initiate RPA, etc. This is the
general-purpose path and it can do anything the orchestrator's tools
support.

### Fast commands — use these instead of chat for known, simple actions

Two slash commands bypass the orchestrator's own reasoning entirely and hit
dedicated fast endpoints instead. Use these whenever you already know
exactly what you want — they're faster and can't fail the way a chat
request asking for the same thing sometimes can (see section 5):

```
you> /summarize ICML 2026        # triggers summarize_indian_authors directly
you> /summary ICML 2026          # fetches an already-generated digest directly, in full
```

`/summarize` starts (or re-confirms) a summarization job for that
conference/year and returns immediately — it doesn't wait for the job to
finish. `/summary` fetches the actual cached digest content once it's done;
run it again later if the job was still in progress. Both require exact
arguments: `/summary <CONFERENCE> <YEAR>`, e.g. `/summary ICML 2026` — the
conference name must match how it's stored in `data/final_output/` on the
server (check with a plain-chat status question if unsure).

Everything else (`run_pipeline`, `get_run_status`, `retry_errors`,
`initiate_form_filler`, `get_rpa_status`, ...) currently only goes through
plain chat — ask for it in natural language.

---

## 3. Re-initializing (key rotation, server URL changes)

If your API key is rotated, or the server URL changes (see section 4 for
why this can happen), delete the saved config and let it re-prompt:

```bash
rm ~/.sentry/config.json
sentry
```

You'll go through the same first-time prompts again.

---

## 4. A note on the server URL changing

If the Mac is currently running SENTRY behind a Cloudflare **Quick Tunnel**
(a URL like `https://random-two-words.trycloudflare.com`, rather than a
proper custom domain), that URL is only stable as long as the tunnel
process itself doesn't restart — a Mac reboot, a crash, or a long enough
network outage will hand out a *new* random URL. If your saved config
suddenly stops connecting, that's the most likely reason. Ask whoever runs
the server for the current URL, then follow section 3 to re-initialize with
it. This will eventually go away once/if the server moves to a real,
stable domain — worth checking with the server operator if this is
happening often.

---

## 5. Updating the client to a new version

The server side of SENTRY (the actual pipeline, the orchestrator, the API)
auto-deploys on every push — you don't need to do anything for that. This
package (the client you run locally) does **not** auto-update; when a new
client version is pushed, you need to manually reinstall:

```bash
pip uninstall sentry-client -y
pip cache purge
pip install --no-cache-dir git+https://github.com/Silajeet0/sentry-api.git
```

(If you installed via `pipx`, use `pipx reinstall sentry-client` instead,
or `pipx uninstall sentry-client` followed by the `pipx install` command
from section 1.)

**Use the full uninstall-then-clean-reinstall sequence above, not just
`pip install --upgrade`.** A plain upgrade from a `git+` URL doesn't
reliably force pip to pull fresh content, and has been known to silently
keep an old, empty, or partial install in place without any obvious error.
The sequence above is the version confirmed to work.

**After reinstalling, verify it actually updated** before assuming it
worked:

```bash
python3 -c "import sentry_client, os; print(os.path.dirname(sentry_client.__file__))"
```

then check the relevant file for whatever feature you're expecting, e.g.:

```bash
grep -n "summarize" <path from above>/cli.py
```

If a new feature you were told about doesn't show up, the reinstall didn't
actually take — repeat the uninstall/purge/reinstall sequence rather than
assuming something else is wrong.

You'll also see a small in-session nudge if the *server's* code changed
mid-conversation (a line like `[sentry] server updated (abc123 -> def456)
since your last message`) — that's about the server, not this package, and
needs no action from you; it's just informational.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'sentry_client'` right after install | Install didn't actually pick up the package contents (stale git history, empty wheel, or a `pip`/interpreter mismatch) | Run `pip show -f sentry-client` — if the `Files:` list is missing `.py` files under `sentry_client/`, the install is broken; do the full reinstall sequence in section 5. Also confirm `which python3` and `which sentry` point into the *same* environment. |
| `[error] 524 Server Error` on a plain chat message | Cloudflare's tunnel has a hard ~100–120 second timeout on any single request; a chat request that takes longer than that (large content generation, a cold-started local model) gets cut off — even though the underlying work may still complete on the server | Prefer `/summarize` and `/summary` (section 2) for the two cases this most commonly hits. For anything else, if you hit this a lot, ask the server operator — this is a known limitation being tracked. |
| A reply seems to answer two unrelated questions at once | Historically caused by a client bug where a failed request left an orphaned, unanswered message in the conversation history, which then got silently bundled into the next question | Fixed in current versions of this client (section 5's reinstall picks up the fix if you're on an old one). If it still happens after reinstalling and verifying via `grep`, it's a new issue — report it. |
| `sentry` prompts for setup again out of nowhere | `~/.sentry/config.json` got deleted or the file is unreadable/corrupted | Just go through setup again (section 1) — no data is lost elsewhere, this file only ever held your key and server URL. |
| A summary/`/summary` command says no digest exists yet | The job hasn't finished, or was never started | Run `/summarize <CONFERENCE> <YEAR>` first, wait, then try `/summary` again. |

---

## 7. Security notes

- Your API key is stored in plaintext at `~/.sentry/config.json`
  (`chmod 600` — owner read/write only, but not encrypted). Don't commit
  this file anywhere, don't paste its contents in chat/Slack/tickets.
- If you ever suspect your key leaked, tell the server operator so it can
  be rotated (removed from the server's `SENTRY_API_KEYS`) — then follow
  section 3 to pick up the new one.
- This is currently a small, trusted-team tool — there's no per-user rate
  limiting or granular permission tiering yet. Be considerate about not
  triggering large/expensive/side-effecting actions (large `run_pipeline`
  runs, `initiate_form_filler`) casually, since they run for real against
  real infrastructure and real external forms.
