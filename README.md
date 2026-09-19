# sentry-client

A thin HTTP client for the SENTRY orchestrator API. This is what
teammates use instead of SSH-ing into the Mac and running
`orchestrator_cli.py` directly — it talks to `orchestrator_api.py` over
HTTPS (through a Cloudflare Tunnel) and needs no checkout of the SENTRY
codebase itself.

Contains no pipeline/scraper/extractor logic — everything real happens
server-side and can change daily without this package needing a new
release.

---

## Install

```bash
pip install -e /path/to/sentry-client
# or, from a wheel/sdist once one exists:
pip install sentry-client
```

This adds a `sentry` command to your shell.

## First run

```bash
sentry
```
On first run you'll be prompted once for your **API key** and the
**server URL** (a `https://*.trycloudflare.com` link — get this from
whoever administers the Mac). Both are saved to `~/.sentry/config.json`
(owner-read/write only) so you won't be asked again.

```
First-time setup — this only happens once.
Enter your SENTRY API key: ****************
Server URL [https://sentry-api.example.org]: https://<current>.trycloudflare.com
Saved to ~/.sentry/config.json
```

## Usage

```
SENTRY orchestrator — type an instruction, '/reconnect' if the server URL has changed, or 'exit' to quit.

you> extract Indian-affiliated authors from ICML 2026
agent> ...
```

Plain input is sent to the orchestrator's chat/tool-calling loop
(`/v1/chat/completions`) — the same thing `orchestrator_cli.py` gives you
on the server itself. A few things bypass that loop on purpose, because
routing them through an LLM generation pass is slower and can time out on
large responses:

| Command | What it does |
|---|---|
| `/summary <CONFERENCE> <YEAR>` | Fetches an already-generated email digest straight off disk (`GET /v1/summary/...`). Use this instead of asking in chat for "show me the summary" of something large. |
| `/summarize <CONFERENCE> <YEAR>` | Starts a summarize job directly (`POST /v1/tools/summarize/...`), skipping the orchestrator LLM entirely. Use this instead of "summarize X" in chat if a cold model load or multi-step tool reasoning risks a slow/timed-out response. |
| `/reconnect` | Clears the saved server URL/API key and re-runs first-time setup. See **Troubleshooting** below — this is the fix for the most common failure mode. |
| `exit` / `quit` | Quit the REPL. |

You can also reset the saved config before even entering the REPL:

```bash
sentry --reconnect
```

---

## Troubleshooting

### `[sentry] couldn't reach https://....trycloudflare.com: ... NameResolutionError ... Failed to resolve ...`

This is by far the most common failure, and it is **not** a client bug,
an outage of the SENTRY code itself, or anything wrong with your API
key. It means the URL this client has saved no longer resolves — either
because the server's public URL rotated to a new one (covered here), or
because the tunnel behind the *same* URL silently died without its
process actually restarting (a "zombie tunnel" — covered in the next
section; check that one first if `pm2 status` claims the tunnel is
`online` and the URL genuinely doesn't resolve from anywhere, including
public DNS like `8.8.8.8`).

**Why this happens:** the Mac exposes `orchestrator_api.py` to the
internet with a Cloudflare **quick tunnel** (`cloudflared tunnel --url
http://localhost:8091`, managed by pm2 as the `sentry-tunnel` process —
see `scripts/ecosystem.config.js` in the main SENTRY repo). Quick
tunnels are free and require no Cloudflare account, but as a trade-off
they have **no fixed hostname** — Cloudflare mints a new random
`*.trycloudflare.com` subdomain every single time the `cloudflared`
process (re)starts, and the old subdomain stops resolving in DNS
entirely the moment the process that owned it goes away (not merely
"connection refused" — the name itself disappears, which is exactly the
`NameResolutionError` / "Failed to resolve" you're seeing). This is
normal, expected `trycloudflare.com` behavior, not a misconfiguration.

The tunnel process restarts — and therefore the URL rotates — whenever:
- the Mac reboots, sleeps for a long stretch, or loses network,
- `cloudflared` itself crashes, or
- someone manually restarts the `sentry-tunnel` pm2 process.

pm2 is configured with `autorestart: true` for `sentry-tunnel`, so it
comes back on its own after a crash — just with a new URL each time.
Your locally cached `~/.sentry/config.json` has no way of knowing this
happened, so it keeps trying the dead hostname until you tell it about
the new one.

**Fix — someone with terminal access to the Mac needs to:**

1. Check that the tunnel (and the API server) are actually running:
   ```bash
   pm2 status
   ```
   Look for `sentry-api`, `sentry-watcher`, and `sentry-tunnel` all
   showing `online`. If pm2 itself doesn't respond, or the processes
   are `stopped`/`errored`, they need to be brought back up first —
   this is a separate problem from the URL rotating (see "The Mac-side
   processes are stopped" below) — before there's any new URL to fetch.
   If `sentry-tunnel` shows `online` but the URL still doesn't resolve
   from anywhere (see next section for how to check), it's a **zombie
   tunnel** — jump to that section's fix instead of step 2 below, then
   come back here.

2. Get the URL for the run that's currently live:
   ```bash
   grep -A2 "Your quick Tunnel" ~/.pm2/logs/sentry-tunnel-error.log | tail -3
   ```
   `cloudflared` logs everything (including its normal startup banner,
   not just errors) to stderr, which is why pm2 files it under
   `-error.log` — that's expected, not a sign anything's wrong. This
   command greps the **whole file**, not just a recent tail, and takes
   the *last* banner block — that matters, because:
   - `pm2 logs sentry-tunnel --lines N --nostream` only looks at the
     last N lines. Right after a restart, `cloudflared` logs a chunk of
     connectivity-precheck output *after* the banner, which can easily
     push the banner itself outside a short `--lines` window — you'll
     see the precheck's "Environment is healthy" summary but no banner
     and wrongly conclude nothing printed yet.
   - a plain `grep -i "trycloudflare.com" ... | tail -1` (no `-A2`, no
     narrowing to the banner text) can just as easily land on an
     unrelated `ERR Request failed` line from days earlier that happens
     to mention the same domain — a failed *request* to an old, dead
     tunnel matches that grep too, and looks like a URL but isn't
     necessarily the current one.

   Cross-check against `pm2 describe sentry-tunnel`'s `uptime`/`created
   at` to make sure the banner you're reading corresponds to the
   process actually running right now.

3. Send the current URL to whoever hit the error.

**Fix — on the client side**, once you have the current URL:

```
you> /reconnect
First-time setup — this only happens once.
Enter your SENTRY API key: ****************
Server URL [https://sentry-api.example.org]: https://<current>.trycloudflare.com
Saved to ~/.sentry/config.json
```

(Your API key hasn't changed — just re-enter the same one. Only the URL
needs to be updated, but `/reconnect` re-prompts for both since it can't
tell which one went stale.)

### `pm2 status` shows `sentry-tunnel` as `online`, but the URL still won't resolve — even from public DNS (`nslookup ... 8.8.8.8`, or a fresh network)

This is a different failure from simple rotation, and worth ruling out
before assuming your config just needs a newer URL. `pm2`'s `autorestart`
only fires when a process actually **exits** — it has no idea whether
`cloudflared`'s tunnel *connection* is still functional. A `cloudflared`
process can stay alive at the OS level (so pm2 reports it as happily
`online`, restart count `0`) while its actual session with Cloudflare's
edge has silently died — after which Cloudflare deprovisions the DNS
name for that dead session. The result: a hostname that returns
`NXDOMAIN` from *every* resolver, including public ones like `8.8.8.8`,
which is your signal that this isn't a caching/local-DNS problem — the
name genuinely doesn't exist anywhere anymore, while pm2 insists the
process is fine.

**Confirm it's this, not just a stale local DNS cache, from the client
machine hitting the error:**
```bash
nslookup <the-url-your-client-has>.trycloudflare.com 8.8.8.8
curl -v https://<the-url-your-client-has>.trycloudflare.com/v1/version
```
If a public resolver (`8.8.8.8`) also returns `NXDOMAIN`, and `curl`
(which bypasses Python/the sentry client entirely) also can't resolve
it, the hostname is genuinely gone — this isn't your machine's fault
and flushing your own DNS cache won't help.

**Then, on the Mac, confirm it's a zombie and not just a slow tunnel:**
check `~/.pm2/logs/sentry-tunnel-error.log` for the last time anything
was logged for that URL at all (grep the URL itself, not just
`trycloudflare.com` — the log can be large on a long-running tunnel, so
look at the *last* matching line's timestamp, not the first). If it
goes quiet days before you hit the error, and `pm2 describe
sentry-tunnel` shows it's been up since around then with `restarts: 0`,
that's the zombie: the process never crashed, so `autorestart` never
had anything to trigger on.

**Fix:** force a restart manually — waiting won't help, since nothing
will restart it on its own:

```bash
pm2 restart sentry-tunnel
```
Then wait ~10–15s (cloudflared runs a connectivity precheck before it's
fully live) and grab the fresh URL the same way as step 2 above —
grep the whole file for the banner, not a short `--lines` tail:
```bash
grep -A2 "Your quick Tunnel" ~/.pm2/logs/sentry-tunnel-error.log | tail -3
```
Sanity-check it before handing it over, from *both* sides — the Mac and
the machine that's actually running `sentry`:
```bash
curl -sS https://<the-new-url>/v1/version
```
Then `/reconnect` on the client as above.

### The Mac-side processes are stopped, or `pm2 status` shows nothing at all

This means pm2's own daemon didn't come back after whatever took the
tunnel down (typically a Mac reboot). `pm2 startup` (which installs a
launchd hook so pm2 itself restarts at boot) is a one-time setup step
that's easy to have skipped — see `scripts/ecosystem.config.js` in the
main SENTRY repo. From the repo root on the Mac:

```bash
pm2 resurrect            # if `pm2 save` was run previously
# or, if that doesn't bring anything back:
pm2 start scripts/ecosystem.config.js
pm2 save
pm2 startup               # one-time; follow the printed sudo command so
                           # this survives future reboots
```

Then continue with step 2 above to grab the freshly printed tunnel URL.

### `[sentry] server updated (abc1234 -> def5678) since your last message`

Not an error — informational. The server restarted onto a new commit
mid-session (the `sentry-watcher` pm2 process does this automatically
when new code lands on the tracked branch). Your conversation history
is still intact client-side; this is just a heads-up in case newer code
changed how your in-progress request behaves.

### `401 Unauthorized` / `Invalid API key`

Your saved key doesn't match anything in the server's `SENTRY_API_KEYS`.
Keys can be rotated server-side independently of the URL; run
`/reconnect` and enter the current key (ask the Mac's admin for it if
you don't have it).

### A request hangs for a long time, or times out

`chat()` uses a 600s client-side timeout because tool-call round-trips
inside a single turn (a cold Ollama model load, multi-step reasoning)
can genuinely take a while — this is expected for anything that goes
through chat. Actual pipeline runs (`run_pipeline`, `retry_errors`,
`initiate_form_filler`, `summarize_indian_authors`) are backgrounded
server-side regardless, so ask the orchestrator for status ("how's the
run going?") rather than waiting on one request.

If you're fetching a large already-generated digest, prefer `/summary`
over asking in chat — see the table above; routing a large digest
through the orchestrator's LLM as a synchronous chat turn can exceed
Cloudflare's proxy read timeout (a 524, not adjustable on quick tunnels)
well before the 600s client timeout is reached.

---

## Config file

`~/.sentry/config.json`:

```json
{
  "api_key": "...",
  "base_url": "https://....trycloudflare.com"
}
```

Deliberately dumb — no keyring/OS-credential-store integration, since
this is a small internal tool, not a public package with a real threat
model around local file storage. Delete the file (or run `/reconnect` /
`sentry --reconnect`) any time the key is rotated or the server URL
changes.
