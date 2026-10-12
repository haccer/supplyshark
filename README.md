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

SupplyShark is a Python-based reconnaissance tool designed to detect package hijacking, dependency confusion, and typosquatting opportunities across multiple package registries.

## 🦈 Origin Story
SupplyShark began as the detection engine for a SaaS platform designed to monitor software supply chains in real-time.

While the commercial platform has been sunset, I have open-sourced the core scanner. This tool automates the process of finding "dangling" or unclaimed packages that match internal company names or popular libraries—a vector often used in **Dependency Confusion** attacks.

> Note: This tool was used to identify critical vulnerabilities in major crypto protocols and Fortune 500 companies via **HackerOne** and **Immunefi**. 💰

## ⚡ Capabilities
SupplyShark automates the cross-referencing of package names against public registries to identify potential takeover targets.

🕵️‍♂️ **Cross-Registry Recon:** Simultaneously queries `npm`, `PyPI`, and `RubyGems` via their public HTTP APIs to see if a package name exists on one but is unregistered on others — including scoped `@scope/package` names on npm.

📦 **User/Org Scanning:** identifying all packages belonging to a specific maintainer or organization to map their supply chain surface area.

📋 **Bulk Scanning:** Scan lists of GitHub accounts (`-l accounts.txt`, one per line) to sweep many targets in one run.

🔍 **GitHub Integration:** Correlates findings with GitHub repository data to identify abandoned projects or maintainer changes.

🤖 **AI-Agent Attack Surface:** Parses MCP server configs (`mcp.json`, `.cursor/mcp.json`, `.gemini/settings.json`, ...) and documentation for commands that AI coding agents execute — `npx`, `bunx`, `uvx`, `pipx`, `poetry add`, `uv add`, `pnpm dlx` — and flags any that reference packages missing from their registry. A missing name in a config an agent follows is a live dependency-confusion target.

🐚 **Docs Command-Injection Surface:** Flags `curl ... | bash` / `wget ... | sh` patterns in READMEs and docs — instructions that execute remote code when followed by a human or an AI agent.

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
```

Use a read-only token. Add `repo` scope if you need to scan private repositories.

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

Results are appended to `results.txt`. Temporary clones are created under `/tmp/.supplyshark` and cleaned up after each run.

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
