# Security Policy

## Scope & Privacy Model

Lexis (`io.github.fatihaydost.lexis`) is local-first, collects **zero telemetry**, and keeps all vocabulary decks, spaced-repetition progress, and history inside your own XDG directories:

- **Local database & configuration:**
  - Vocabulary decks, SRS scheduling state, and answer history live in `~/.local/share/lexis/lexis.sqlite`.
  - Non-secret UI preferences live in `~/.config/lexis/settings.json`.
  - QML communicates with `backend/lexis_cli.py` by passing JSON payloads over `stdin` rather than command-line arguments (`/proc/<pid>/cmdline`).
- **Primary Free Dictionary lookup (optional, enabled by default):**
  - When you add a word without a meaning or use the `Translate` tab with `AI: Off`, Lexis queries open HTTPS dictionary/sentence endpoints (`https://freedictionaryapi.com/api/v1/entries/`, `https://tatoeba.org/en/api_v0/search`, and `https://api.mymemory.translated.net/get`) strictly for that word or text.
  - You can turn off `Primary Free Dictionary` in `Settings` for strictly offline operation.
- **Optional CLI AI subscriptions (`agy`, `claude`, `codex`):**
  - Disabled (`Off`) by default.
  - When enabled by the user, Lexis invokes the user's already-authenticated CLI (`agy`, `claude`, or `codex`) in read-only, tool-free, non-persistent mode (`--tools ""`, `--no-session-persistence`, `--sandbox read-only`, `--ephemeral`) using each provider's lowest-quota model (`gemini-3.8-flash-low`, `claude-haiku-5-5`, `gpt-5.6-luna`). Lexis never reads or stores CLI OAuth tokens.
- **Optional Local / Custom OpenAI-compatible (`/v1`) endpoint:**
  - Designed for local model servers (`Ollama`, `LM Studio`, `llama.cpp` on `127.0.0.1`), which require no API key.
  - If you save an optional API key for a remote `/v1` router (such as OpenRouter), it is stored exclusively in `~/.local/state/lexis/api_key` inside a `0700` state directory with `0600` (`rw-------`) file permissions — never in `settings.json`, SQLite, or UI snapshots — and clicking **Clear** deletes the file immediately.
- **Privilege boundary:**
  - Nothing runs with elevated privileges, no system services or package managers are invoked, and no files outside Lexis's own XDG directories (or an export path you explicitly pick in `zenity`) are modified.

## Reporting a Vulnerability

If you discover a security issue (such as credential exposure, unintended command execution, or unintended file access), please report it privately via GitHub Security Advisories on [`fatihaydost/omarchy-lexis`](https://github.com/fatihaydost/omarchy-lexis/security/advisories/new) or by emailing **fatihaydostt@gmail.com** rather than opening a public issue.

Include the plugin version from `manifest.json` and steps to reproduce.
