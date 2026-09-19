# Local AI model inside Codex CLI (Windows)

Set up a coding model that runs **on your own laptop** and plug it into the Codex
CLI as a separate profile. When ChatGPT tells you you're out of Codex usage, you
switch to the local model and keep working — no internet, no limits, no cost.

This is the setup shown in the Instagram reel by
[@megareef.ai](https://www.instagram.com/megareef.ai/): *"Codex has a hidden
feature to keep working on your plan."*

---

## What the reel actually shows

Codex CLI isn't locked to OpenAI's servers. Its config supports **custom model
providers** — any endpoint that speaks the OpenAI API. In the video he `cat`s a
config file containing:

```toml
model          = "cerebras/qwen-3-…"
model_provider = "bifrost"
model_context_window = 131072

[model_providers.bifrost]
name     = "Bifrost"
base_url = "http://127.0.0.1:8080/v1"
wire_api = "responses"
```

`base_url` points at `127.0.0.1` — his own machine. He then hits his Codex usage
limit ("You're out of Codex and Work usage… rate limit resets 19 Sept 18:10")
and carries on regardless, because Codex is now talking to a local server. At
the end he shows [llama.cpp](https://github.com/ggml-org/llama.cpp) as what he
recommends for serving models locally.

This setup does the same thing with **Ollama** instead of llama.cpp + Bifrost.
Ollama is one signed installer, manages models for you, serves the same
OpenAI-compatible API, and uninstalls cleanly — which matters more than shaving
a few tokens per second.

---

## How this is kept safe

You asked for no data loss and nothing broken. The design reflects that:

| Risk | How it's handled |
|---|---|
| Your existing Codex config gets mangled | **`config.toml` is never opened for writing.** The setup writes a *separate* file, `~/.codex/local.config.toml`, which Codex only reads when you pass `--profile local`. The installer SHA-256 hashes `config.toml` before and after and aborts loudly if it differs. |
| Losing settings | Your whole `~/.codex` folder is copied to `~/.codex.backup-<timestamp>` before the first change. |
| Half-finished install | All checks run **before** any change. If a check fails, nothing has been written yet. |
| Can't undo it | Every change is recorded in a manifest; `Uninstall-CodexLocalAI.ps1` reverses exactly those and nothing else. |
| System-wide damage | Only **User**-scope environment variables. No Machine scope, no admin rights, no registry edits, no PATH surgery. |
| Laptop freezes under a too-big model | The model is chosen from your actual RAM, and you're warned if under 6 GB would be left for Windows and your other apps. |
| Codex hangs on the local model | The single most common cause is Ollama's context window defaulting to 4096 tokens while Codex needs ≥ 65536. The installer sets `OLLAMA_CONTEXT_LENGTH=65536` and verifies what's actually in force. |
| Your normal `codex` stops working | It can't. Plain `codex` doesn't read the profile file at all. |

---

## Before you start

You need:

- **Windows 10 or 11**
- **~25 GB free disk** (the model is about 14 GB)
- **Node.js** — only if you don't already have Codex. Get the LTS build from
  [nodejs.org](https://nodejs.org). Check with `node --version`.

You do **not** need admin rights, and you do **not** need to uninstall anything.

On your machine (24 GB RAM) the installer will pick **`gpt-oss:20b`** — OpenAI's
open-weight 20B model. It's a mixture-of-experts design, so it's much faster
than its size suggests, and it's the model OpenAI documents for Codex.

---

## Running it

Open **PowerShell** (no need for Administrator) and `cd` to this folder.

### 1. See what it would do — changes nothing

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-CodexLocalAI.ps1 -DryRun
```

This prints every check and the full plan, then exits. Read it. Nothing on your
machine has been touched.

> **If you get "running scripts is disabled on this system"** — that's Windows'
> default script policy. The `-ExecutionPolicy Bypass` above handles it for that
> one command without changing your system setting. If you downloaded these
> files rather than cloning the repo, also run
> `Unblock-File .\*.ps1` first.

### 2. Do it for real

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-CodexLocalAI.ps1
```

It shows the plan again and waits for you to type `y`. Then it installs Ollama
(if needed), installs the Codex CLI (if needed), sets the context window,
downloads the model, tests that the model actually answers, writes the profile,
and proves your `config.toml` is byte-identical.

The model download is the slow part — 14 GB. Leave it running.

### 3. Check it's healthy any time

```powershell
powershell -ExecutionPolicy Bypass -File .\Test-CodexLocalAI.ps1
```

Read-only. Walks every link in the chain and tells you which one is broken, with
the fix.

---

## Using it day to day

Two commands:

```powershell
codex
```
Unchanged. Your ChatGPT account, exactly as before.

```powershell
codex --profile local
```
Your own laptop. Use it when you've hit your usage limit.

There's also Codex's built-in Ollama mode, which needs no config file at all and
is a useful fallback if the profile ever misbehaves:

```powershell
codex --oss -m gpt-oss:20b
```

### Options worth knowing

```powershell
# A smaller, faster model if 20B feels heavy while Rhino is open
.\Install-CodexLocalAI.ps1 -Model qwen2.5-coder:7b

# Name the profile something else
.\Install-CodexLocalAI.ps1 -ProfileName offline   # -> codex --profile offline

# Bigger context (uses more RAM)
.\Install-CodexLocalAI.ps1 -ContextLength 131072
```

---

## Undoing it

```powershell
powershell -ExecutionPolicy Bypass -File .\Uninstall-CodexLocalAI.ps1
```

Removes the profile file, restores the environment variable to whatever it was,
deletes the state folder. Keeps the model (re-downloading 14 GB is painful) and
keeps your backup.

```powershell
# also delete the 14 GB model
.\Uninstall-CodexLocalAI.ps1 -RemoveModel

# also uninstall Ollama, but only if this script installed it
.\Uninstall-CodexLocalAI.ps1 -RemoveModel -RemoveOllama
```

Your `config.toml` is untouched by all of this, because it was never edited.

---

## If something goes wrong

**"running scripts is disabled on this system"**
Use the `powershell -ExecutionPolicy Bypass -File …` form shown above.

**`ollama` or `codex` not found straight after installing**
PATH changes only reach *new* windows. Close PowerShell, open a fresh one, re-run.
The installer is safe to re-run; it skips what's already done.

**Codex hangs or errors on the local profile**
Almost always the context window. Run `Test-CodexLocalAI.ps1` — it checks this
explicitly. If `OLLAMA_CONTEXT_LENGTH` is missing or below 65536, re-run the
installer and restart Ollama.

**Everything crawls, the laptop is thrashing**
The model is competing with Rhino/Illustrator for RAM. Either close those, or
switch down: `.\Install-CodexLocalAI.ps1 -Model qwen2.5-coder:7b`.

**Port 11434 already in use**
Preflight catches this and stops rather than fighting whatever owns the port.

**Want your old setup back immediately**
Your backup is at `~/.codex.backup-<timestamp>`. Copy it back over `~/.codex`.

---

## Honest expectations

A 20B model on a laptop is **not** GPT-5. Being straight about it:

- **Good at**: continuing work along a plan that's already laid out, mechanical
  edits, boilerplate, renaming, filling in obvious code, explaining code.
- **Weaker at**: starting hard problems from scratch, long multi-file
  refactors, subtle debugging, holding a very large codebase in its head.
- **Speed**: with an NVIDIA GPU, quick. CPU-only on 24 GB, expect roughly
  5–15 tokens/second — usable, but you'll notice it.

Treat it as the thing that keeps you moving until your quota resets, which is
exactly how the reel frames it.

---

## Sources

- [Ollama — Codex CLI integration](https://github.com/ollama/ollama/blob/main/docs/integrations/codex.mdx) — the `wire_api`, `base_url` and profile format used here, and the ≥ 64k context requirement
- [Ollama — context length](https://docs.ollama.com/context-length) — why the default can be 4096
- [Codex CLI — advanced configuration](https://developers.openai.com/codex/config-advanced) — custom providers and profiles
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — the alternative shown at the end of the reel
