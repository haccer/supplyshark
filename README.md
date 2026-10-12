# supplyshark


                   /""-._
                  .      '-,
                  :         '',
                  ;      *     '.
                  ' *         () '.
                   \               \
                    \      _.---.._ '.
                     :  .' _.--''-''  \ ,'
       .._            '/.'             . ;
        ; `-.          ,                \'
         ;   `,         ;              ._\
          ;    \     _,-'                ''--._
           :    \_,-'                          '-._
            \ ,-'                       .          '-._
           .'         __.-'';            \...,__       '.
          .'      _,-'       \              \   ''--.,__ '\
         /   _,--' ;          \             ;           "^.}
        ;_,-' )     \  )\      )            ;
             /       \/  \_.,-'             ;
            /                              ;
         ,-'  _,-'''-.    ,-.,            ;
      ,-' _.-'        \  /    |/'-._...--'
     :--``             )/

          - - - {  S U P P L Y  S H A R K  } - - -

SupplyShark is a Python-based reconnaissance tool that finds **takeover targets in public code**: package names, npm scopes, and domains that are referenced by GitHub repositories but unclaimed on their registry. Register the name, capture the reference — the dependency-confusion class of attack, plus its AI-era extensions. Every finding is verified claimable before it's reported; if a line lands in `results.txt`, registering something gets you code execution somewhere.

## 🦈 Origin Story
SupplyShark began as the detection engine for a SaaS platform designed to monitor software supply chains in real-time.

While the commercial platform has been sunset, I have open-sourced the core scanner. This tool automates the process of finding "dangling" or unclaimed packages that match internal company names or popular libraries—a vector often used in **Dependency Confusion** attacks.

> Note: This tool was used to identify critical vulnerabilities in major crypto protocols and Fortune 500 companies via **HackerOne** and **Immunefi**. 💰

## ⚡ Capabilities
SupplyShark automates the cross-referencing of package names against public registries to identify potential takeover targets.

🕵️‍♂️ **Cross-Registry Recon:** Simultaneously queries `npm`, `PyPI`, and `RubyGems` via their public HTTP APIs to see if a package name exists on one but is unregistered on others. Scoped npm packages are only reported when their scope is unpopulated — a missing package under a live org (like `@openzeppelin`) can't be claimed by anyone else, so those are dropped automatically.

📦 **Account Scanning:** Clones and sweeps every non-forked, non-archived repo of a GitHub user or org — dependency manifests (`package.json`, `requirements*.txt`, `pyproject.toml`, `Gemfile`), docs, CI workflows, and agent configs alike.

📋 **Bulk Scanning:** Scan lists of GitHub accounts (`-l accounts.txt`, one per line) to sweep hundreds of targets in one run. One bad account never kills the sweep.

🔍 **GitHub Integration:** Repo discovery and cloning via token, findings cited with `blob/<default-branch>` permalinks ready for reports.

🤖 **AI-Agent Attack Surface:** Parses MCP server configs (`mcp.json`, `.cursor/mcp.json`, `claude_desktop_config.json`, `.gemini/settings.json`, ...) and agent instruction files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `.github/copilot-instructions.md`, ...) for commands AI coding agents execute — `npx`, `bunx`, `uvx`, `pipx`, `uv run --with`, `python -m`, `poetry add`, `uv add`, `pnpm dlx` — and flags any that reference packages missing from their registry. Remote MCP server URLs are checked for claimable domains (re-registration = the agent's connection gets taken over).

🏷️ **Surface Tags:** Findings carry where they live: `:agent` (instruction files agents follow automatically) and `:ci` (GitHub Actions workflows — executes on push). `[pip:agent]` reads very differently from `[pip]`.

🌐 **Unregistered-Domain Takeover Surface:** Collects every hostname referenced by an http(s) URL across configs and docs (`.npmrc`, `pip.conf`, `renovate.json`, install instructions, ...) and reports only domains verified claimable: registrable apex dead in DNS **and** unregistered per RDAP. Registered-but-undelegated domains, dead subdomains under live apexes, and placeholder hosts are filtered out automatically — if it appears in results, registering it captures something.

## 🎯 What gets reported

Six finding classes, all verified claimable first — nothing informational, nothing you can't act on:

| Label | Finding | Verified by |
|---|---|---|
| `[npm]` | Unscoped npm name referenced in code/docs but unregistered | registry 404 |
| `[npm scope]` | Unclaimed npm scope — one registration claims every listed package | profile 404 + package-existence probe |
| `[pip]` | PyPI name unregistered (PEP 503 normalized) | PyPI JSON API 404 |
| `[gem]` | RubyGems name unregistered | RubyGems API 404 |
| `[mcp-url]` | MCP server endpoint on a claimable domain | DNS + RDAP |
| `[domain]` | Any referenced hostname on a claimable domain (registrable apex dead AND unregistered) | DNS + RDAP |

Modifiers: `:agent` (reference lives in an instruction file agents follow automatically — `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, ...) and `:ci` (lives in a GitHub Actions workflow — executes on push). `[npm scope]` findings list every covered package and carry `[scope ownership unverified]` when npm's bot protection blocked the account check — verify by hand before acting on those.

Everything else is filtered out on purpose: missing packages under live scopes (not claimable), versioned spellings (`pkg@1.2`), git/file dependency refs, `node_modules`, placeholder hosts and invented TLDs, registered-but-dead domains, and dead subdomains under live apexes.

## Prerequisites

- Python 3.10+ (3.11+ for `pyproject.toml` dependency parsing)
- ripgrep (`rg`)

All registry availability checks use the public HTTP APIs (PyPI JSON API, npm registry, RubyGems API) — no `npm`, `gem`, or `poetry` CLIs required.

## Install

```
pip install -r requirements.txt
```

## Configure

Create a `.env` file (see `env.sample`) with a GitHub token:

```
GITHUB_AUTH=ghp_...
# Optional: raises npm registry rate limits for mass scans
NPM_TOKEN=npm_...
```

Use a read-only GitHub token — a classic PAT with zero scopes is enough for public scanning (5000 API req/hr vs 60 unauthenticated). Add `repo` scope only if you need to scan private repositories. PyPI and RubyGems have no auth concept for read-only lookups; npm does, hence the optional token. Rebuild the bounty target list with `python scripts/build_bbp.py`.

## Usage

Scan all repos for a GitHub account:

```
python supplyshark.py -u <github_account>
```

Scan a single repo:

```
python supplyshark.py -u <github_account> -r <repo_name>
```

Scan a list of accounts (one per line):

```
python supplyshark.py -l accounts.txt
```

Results are appended to `results.txt`. Temporary clones are created under `/tmp/.supplyshark` and cleaned up after each run. For long sweeps, run inside tmux with unbuffered output captured to a log:

```
python -u supplyshark.py -l bbp.txt 2>&1 | tee scan.log
```

Ctrl-C is safe and re-running resumes cheaply — registry answers persist in a 30-day disk cache, so already-checked names are never re-queried.

## 🧪 Tests

The fixture cases from the original `supplyshark/tests` vulnerable repo live in `tests/` as a hermetic pytest suite — no network, registries faked, so it runs in seconds and is CI-safe:

```
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Opt-in live smoke tests against the real registries (6 requests, also validates the cache):

```
pytest -m live
```

## 🐌 Rate Limits

All registry checks are direct HTTP with three protections baked in (`shark/registry.py`):

- **Concurrency cap** — at most 10 in-flight registry requests per run
- **Retry with backoff** — 429/5xx answers are retried up to 3 times with exponential backoff, honoring `Retry-After`
- **30-day disk cache** — definitive 200/404 answers persist at `/tmp/.supplyshark/registry-cache.json`, so repeat scans of the same accounts don't re-query (delete the file to force fresh checks)

Only an explicit 404 counts as "available" — rate-limited or failed lookups are treated as taken, so throttling degrades recall, never correctness.

## ⚠️ Legal Disclaimer
**For Educational and Defensive Use Only.** This tool is intended to help security professionals secure their own infrastructure or participate in authorized bug bounty programs. Using this tool to register malicious packages or attack targets without permission is illegal. The author assumes no liability for misuse.

## 🤝 Contributing
We welcome contributions from the security community!

## 📄 License
MIT License. See `LICENSE`.

---

A cybersecurity tool by [@haccer](https://github.com/haccer)
