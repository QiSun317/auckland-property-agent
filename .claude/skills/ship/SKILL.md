---
name: ship
description: Publish any change to this repo all the way to the live site, so the effect is visible on the public page rather than only on the laptop. Use this after making ANY code change here — to scripts/, the page template, evals, or ops/worker/ — even when the user did not say "publish", and even for a one-line fix. The user's standing instruction is that every change goes straight to the remote and gets re-deployed; a change that only exists locally is not finished. Also use it whenever they say 上线 / 发布 / 推上去 / push it / deploy / "make it live".
---

# Shipping this project

The user works by looking at the **live page**, not at a local file. A change
that builds cleanly on the laptop but has not been published does not exist to
them, and reporting it as done is misleading. So the finish line for every
change here is: pushed to both remotes, and the public URL verified to be
serving that exact build.

Their standing instruction, in their words: *每次改动都要直接 push 到远程，并且
重新进行上线。我要直接在远程就能够看到修改效果。*

## The one command

```bash
.claude/skills/ship/scripts/ship.sh "Let the assistant carry a conversation"
```

That runs the whole sequence and refuses to publish if anything is off. Prefer
it over doing the steps by hand — its checks exist because each one has caught a
real failure. Read on for what it does and why, which you need when it stops.

## What it does, and why in that order

1. **Build with `AKL_AGENT_PROXY` set.** Building without it writes
   `"proxy":""` into the page, which flips `MODEL_ON` to false and silently
   turns the assistant back into rules-only. No error, no warning — the page
   just quietly loses the model. It shipped that way for weeks without anyone
   noticing. The script defaults the value and then greps the built file to
   confirm it landed.
2. **Run the gate suite against the built page.** Build first, then test: the
   suite loads `heatmap.html` through jsdom so it exercises the code that
   actually ships rather than a copy. Testing before building would grade the
   previous build, pass, and ship something else.
3. **Commit and push the source repo** (`QiSun317/auckland-property-agent`,
   private — holds the scrapers and address-level valuations).
4. **Publish the page** via `ops/publish.sh`, which pushes the built HTML to
   `QiSun317/auckland-house-heatmap` (public, GitHub Pages).
5. **Verify the live URL** by comparing its SHA-256 against the local build,
   retrying while Pages finishes. Without this you are reporting success on
   faith; Pages lags by a minute or two and occasionally fails outright.

## Two remotes, and the worker is a third target

| what | where | how |
|---|---|---|
| source | `QiSun317/auckland-property-agent` (private) | `git push origin main` |
| public page | `QiSun317/auckland-house-heatmap` (public) | `ops/publish.sh` |
| model proxy | Cloudflare Worker `auckland-suburb-agent` | `npx wrangler deploy` |

**The worker does not ship with the page.** If you changed anything under
`ops/worker/`, the page will go out talking to the old worker. Deploy it first:

```bash
cd ops/worker && npx wrangler deploy
```

Expect this to need its own approval — it publishes to the public internet, and
the harness stops it by default. If it is refused, hand the command to the user
rather than trying to route around it. `ship.sh` detects worker changes and
warns instead of running the deploy itself, so that a refusal cannot take the
whole script down with it.

Live proxy URL: `https://auckland-suburb-agent.qisun317.workers.dev`

## Writing the message

It becomes the commit subject in both repos, and the site repo's history is the
only record of what the public page actually gained. `ops/publish.sh` defaults
to "Refresh data", which is a lie when the page grew a feature — so always pass
one. Match the existing style: a plain statement of what the page can now do.

- `Let the assistant carry a conversation`
- `Every figure says what it measures`
- `Read the suburb intros into fields the rules can use`

Not `Update template` or `Fix bug` — those say nothing to someone reading the
history six months later.

## When the suite fails

Do not publish, and do not weaken a case to get green. Every case in
`evals/cases.jsonl` is a failure that actually happened on this page; the file
is a record of the ways this thing has been wrong, in a form that makes being
wrong that way again into a red build. A failing gate means either a real
regression, or that the intended behaviour genuinely changed — in which case
update the case *and say so explicitly to the user*, with the reasoning.

## After it is live

Say what changed and give the URL. When the change is something the user can
see and click — assistant behaviour, a new card, different copy — check it in a
real browser before declaring victory, because the gates verify data and text
but not that the thing renders and responds:

```
https://QiSun317.github.io/auckland-house-heatmap/
```

Driving the live assistant costs a real Gemini call (~$0.009 per question, the
full 205-suburb table goes up every time), which is cheap enough that verifying
beats guessing.
