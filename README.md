# Git Commit Bard

*Your staged diff, returned as verse. The commit message as a tiny creative artifact.*

Git Commit Bard reads your staged diff and writes the commit message with
literary flair — haiku, sea shanty, limerick, epic verse, ballad, pirate,
corporate-buzzword, noir. Whimsy is opt-in. It runs with **zero setup** in an
offline mock mode, and calls a real model the moment you add an API key.

> **Status: alpha.** The standalone CLI works today (`--sample`,
> `--list-styles`, and real-model verse when an API key is set). A
> `prepare-commit-msg` git hook and a default "dual" mode — a clean
> Conventional-Commit subject line with the verse in the body — are in progress.

## Try it in 30 seconds

No API key required — it runs in a charming offline mock mode out of the box.

> Not on PyPI yet — `pipx install commit-bard` lands with the first release;
> for now clone and install from source.

```bash
git clone https://github.com/Lonkins/commit-bard
cd commit-bard
python3 -m pip install -e .          # or: pipx install .

commit-bard --sample --style shanty  # a sea shanty about a bundled sample diff
commit-bard --list-styles            # see all the styles
commit-bard --sample 3               # three styles side by side (great screenshot)
```

A taste — one haiku `commit-bard --sample --style haiku` might print (the mock
corpus rotates, so you'll get a different verse each run):

```
Comments fall like leaves—
the parser walks a clean path,
green tests rise at dawn.
```

## Real diffs, real models

Stage some changes and pick a style. With no key it stays in mock mode; drop a
key in and the **same command** calls a real model and versifies *your* diff:

```bash
git add -p
export ANTHROPIC_API_KEY=sk-...      # or OPENAI_API_KEY=...
commit-bard --style noir             # a hard-boiled verse about what you staged
```

The artifact goes to **stdout** (pipe-clean), so you can wire it straight in:

```bash
git commit -m "$(commit-bard --style limerick)"
```

## Providers & configuration

Configured entirely by environment variables. **Auto-detect:** no key → mock;
one key → it just works.

| Variable | Meaning | Default |
|---|---|---|
| `COMMIT_BARD_PROVIDER` | `anthropic` \| `openai-compatible` \| `ollama` \| `mock` | auto-detect → `mock` |
| `COMMIT_BARD_MODEL` | model name override | per-provider default (illustrative) |
| `COMMIT_BARD_API_KEY` | generic API key | — |
| `COMMIT_BARD_BASE_URL` | base URL override (proxies, gateways, self-host) | per-provider default |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | honored as fallbacks; presence drives auto-detect | — |

- **`openai-compatible` covers a lot:** OpenAI itself, any OpenAI-compatible
  gateway/proxy, and local **Ollama** (`COMMIT_BARD_PROVIDER=ollama`,
  base URL `http://localhost:11434/v1`).
- **Model defaults are illustrative and change often** — always overridable via
  `COMMIT_BARD_MODEL`. Don't treat the built-in defaults as authoritative.
- **API keys are read from the environment only**, never written to a config
  file.

## Privacy — read this

Versifying with a **real provider sends your staged diff to that provider** —
the same reality as every AI-commit tool. Be deliberate about it:

- **Mock mode sends nothing** and is the default with no key.
- For local-only verse, point it at **Ollama** so nothing leaves your machine.
- The diff can contain secrets; we can't reliably scrub them. Prefer mock/local
  when in doubt, and never auto-run this in CI without explicit opt-in.

## Prior art & honest positioning

AI-generated commit messages are a mature, crowded space, and Git Commit Bard
does **not** claim to have invented the pipeline. Credit where it's due:

- [**aicommits**](https://github.com/Nutlope/aicommits) — popular, clean, fast.
- [**opencommit**](https://github.com/di-sukharev/opencommit) — multi-provider; GitHub 2023 Hackathon winner.
- [**aicommit2**](https://github.com/tak-bro/aicommit2) — multi-provider, multiple candidates.

The whole `diff → LLM → message` flow (multi-provider, git hook) is well-trodden
and not novel. **Git Commit Bard is a joy layer on top of a solved problem.**
What's ours: treating the commit as a deliberate literary/genre artifact, a
playful-yet-useful dual mode, and a delight layer (a repo "wrapped" of your best
commit poems, a shareable gallery) around it. We win on charm and taste, not on
inventing the plumbing.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                # fully offline; no key, no network
```

Stdlib only at runtime (Python 3.9+) — the provider calls use `urllib`, so
`pipx install` stays instant and the offline demo needs nothing.

## License

[MIT](LICENSE).
