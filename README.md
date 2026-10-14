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

Finds **takeover targets in public code**: package names, npm scopes, and
domains referenced by GitHub repositories but unclaimed on their registry.
Every finding is verified claimable before it's reported.

## What it finds

| Label | Finding | Verified by |
|---|---|---|
| `[npm]` | npm name referenced but unregistered | registry 404 |
| `[npm scope]` | Unclaimed npm scope — one registration claims every listed package | profile 404 + probe |
| `[pip]` | PyPI name unregistered (PEP 503 normalized) | PyPI API 404 |
| `[gem]` | RubyGems name unregistered | RubyGems API 404 |
| `[mcp-url]` | MCP server endpoint on a claimable domain | DNS + RDAP |
| `[domain]` | Referenced hostname on a claimable domain | DNS + RDAP |

Modifiers: `:agent` (instruction file agents follow), `:ci` (GitHub
Actions workflow), and npm exec-path tags `:runner` (npx/bunx),
`:dep` (runtime dependency), `:dev` (devDependency).

**When does a taken-over npm name execute?** (npm 12 blocks dependency
install scripts by default; verified against npm 11.19 and 12.2 with
`scripts/verify_npm_exec_paths.sh` / `scripts/demo_npm_rce.sh`):

| Victim action | npm < 12 | npm 12+ |
|---|---|---|
| `npm install <x>` alone | RCE at install | delivered, no execution yet |
| `npm install <x>`, victim's own scripts then invoke the bin | RCE at install | **RCE** (root scripts not gated; `.bin` on their PATH) |
| `npm install` (full), victim's postinstall invokes the bin | RCE at install | **RCE during install** |
| `npx <x>` | RCE | **RCE** |
| app imports the dependency | RCE | **RCE** (import-time) |
| `npm install -g <x>`, then running `<x>` | RCE at install | **RCE on invocation** (bin linked) |

Proof per path: `scripts/demo_npm_rce.sh <name> <runner|dep|tool|ownscript|global>`.
PyPI and RubyGems have no equivalent gating — install-time RCE unchanged.

Scans every non-forked, non-archived repo of an account: dependency
manifests, docs, CI workflows, and agent configs (`mcp.json`,
`claude_desktop_config.json`, ...) — including the commands AI coding
agents execute (`npx`, `uvx`, `python -m`, ...).

## False-positive suppression

Junk dies before any registry request: names must pass `shark/validate.py`
registry grammars (stopwords, placeholder vocabulary, version strings,
node core modules), `spec/`/`test/`/`fixtures/` trees are excluded,
`[tool.uv.sources]` git/path redirects are skipped, `npx` names shadowed
by locally-declared bins are suppressed, `.npmrc`-pinned scopes are
dropped, and prose files named `requirements*.txt` are content-sniffed.
Rules are corpus-tuned with regression tests — see `tests/test_validate.py`.

## Usage

```
pip install -r requirements.txt
```

Prerequisites: Python 3.10+ (3.11+ for pyproject parsing), ripgrep.
Create `.env` with `GITHUB_AUTH=ghp_...` (read-only token; see `env.sample`).

```
python supplyshark.py -u <account>                  # one account
python supplyshark.py -u <account> -r <repo>        # one repo
python supplyshark.py -l accounts.txt --resume      # sweep, resumable
python supplyshark.py -u <account> --npm --pip      # registry subset
python supplyshark.py -u <account> --dead-domains   # + DNS/RDAP checks
```

Results append to `results.txt` with `blob/<branch>` permalinks.
Registry answers cache for 30 days; Ctrl-C is safe and re-runs resume
cheaply. Registry checks are concurrency-capped with retry/backoff, and
only explicit 404s count as claimable — throttling degrades recall,
never correctness. Rebuild the bounty-program target list with
`python scripts/build_bbp.py`.

## Triage with an AI agent

`AGENTS.md` is written for AI coding agents (auto-discovered by Claude
Code, Cursor, and similar tools) and humans alike. It contains the full
findings-to-report workflow: context triage, docs/cross-org/bug-bounty
scope checks, the measured npm 12 execution model, and the local-PoC
safety rules. Research work products stay in gitignored `triage/`.

## Validating findings — PoC packages & the fake registry

**For educational and authorized-testing use only.**

- [`scripts/fake_registry.py`](scripts/fake_registry.py) — a localhost
  stand-in for npm/PyPI/RubyGems. Serves any name a victim's package
  manager asks about, logs every resolution, delivers marker payloads.
  Proves dependency confusion end to end — including registry-priority
  scenarios against a scratch copy of a victim repo — without uploading
  anything to a real registry.
- [`poc_packages/`](poc_packages/README.md) — PoC packages per registry
  (npm/PyPI/RubyGems) in three categories: `dns` (install-time canary),
  `placeholder` (inert name-holder for coordinated disclosure), `rce`
  (code execution at the registry's earliest execution point: npm
  `preinstall`, PyPI sdist `setup.py`, RubyGems `extconf.rb`).

When a new npm/pnpm/yarn version drops, re-measure client behavior with
`scripts/verify_npm_exec_paths.sh` before making install-script impact
claims. See [poc_packages/README.md](poc_packages/README.md) for commands,
per-registry execution-point differences, and safety rules. Never publish
to a real registry except deliberate, human-approved placeholders during
disclosure.

## Tests

Hermetic (no network, registries faked):

```
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Live smoke tests (6 requests): `pytest -m live`.

## Legal

**For educational and defensive use only.** Intended for securing your
own infrastructure or authorized bug bounty programs. Registering
malicious packages or attacking targets without permission is illegal.

MIT License. A tool by [@haccer](https://github.com/haccer).
