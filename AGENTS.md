# AGENTS.md — working in this repository

Guidance for AI coding agents (and humans) working on SupplyShark: how to
scan, how to triage findings into reports, and the hard safety rules.

## What this tool is

SupplyShark finds takeover targets in public code: package names, npm
scopes, and domains referenced by GitHub repos but unclaimed on their
registry. Every finding that reaches `results.txt` is verified claimable.
The core contract: **junk never reaches a registry request and never
reaches output.** `shark/validate.py` enforces the name-level half of that
(see "Changing the filters" below).

## Repository layout

- `shark/` — scanner core (extraction streams, registry clients,
  `validate.py` name rules, result formatting)
- `supplyshark.py` — CLI entrypoint
- `scripts/build_bbp.py` — rebuild the bounty-program target list
- `scripts/fake_registry.py` — localhost npm/PyPI/RubyGems stand-in for
  validating dependency confusion without touching real registries
- `poc_packages/` — per-registry PoC packages (dns / placeholder / rce)
- `tests/` — hermetic pytest suite (fake registries, in-repo fixtures)
- `lists/` — account lists for sweeps (`bbp.txt` is generated)
- `triage/` — research work products (GITIGNORED; never commit)

## Operating the scanner

```
python supplyshark.py -u <github_account>            # one account
python supplyshark.py -l lists/bbp.txt --resume      # bounty-program sweep
python supplyshark.py -u <account> --dead-domains    # + DNS/RDAP checks
python supplyshark.py -u <account> --gem             # one registry only
python supplyshark.py -u <account> --npm --pip       # subset of registries
```

Rebuild the bounty target list with `python scripts/build_bbp.py` (pulls
HackerOne/Bugcrowd/YesWeHack/Immunefi policy data; `lists/exclude.txt`
survives regeneration). Registry answers are cached 30 days under
`/tmp/.supplyshark/registry-cache.json`.

## Triage workflow (results.txt → submittable reports)

`results.txt` lines are the START of the work, not the end. Triage in
this order, keeping notes per finding (verdict + evidence at file:line):

1. **Context triage** — fetch every cited file; judge WHERE the reference
   lives (dependency manifest / CI workflow / agent-instruction file /
   README / script) and WHO executes it (build-time install, CI on push,
   agent following instructions, human copy-paste), and record the
   EXECUTION PATH (see "npm exec paths & severity" below — npm findings
   carry `:runner`/`:dep`/`:dev` tags). Kill anything that
   doesn't execute from the public registry in context:
   - `npx NAME` where a declared dependency provides that bin (local
     resolution wins — the scanner now detects the common cases),
   - dependencies redirected by `[tool.uv.sources]` git/path/url,
   - scopes pinned to a private registry via `.npmrc`,
   - placeholder/tutorial names, fixtures, vendored docs.
2. **Docs exposure** — check the org's live docs (docs.*, *.github.io,
   readthedocs) for the name in install commands; company-domain evidence
   beats github.io; verify corporate domains absent before settling for
   github.io evidence. Word collisions don't count.
3. **Cross-org usage** — GitHub code search for other orgs genuinely
   installing the name (forks excluded); a bounty-program org using the
   name is an additional reporting channel.
4. **Bug-bounty fit** — find the org's program (policy data + SECURITY.md
   + security.txt + web search), then PROVE scope: read the actual in-
   scope asset list. Domain-only scope needs a written chain from the
   takeover to those domains. Immunefi: `smart_contract`-category assets
   are out for this bug class; `blockchain_dlt` needs a PoC proving a
   listed impact.
5. **PoC (when impact must be shown)** — prove the confusion flow with
   `python3 scripts/fake_registry.py`: point a scratch copy of the
   victim's install at it (`--registry` / `--index-url` / `--source`),
   confirm the `RESOLVED` log line and the marker file. For npm findings
   use `scripts/demo_npm_rce.sh <name> <tag>` (one command, works on
   npm 12; `TARBALL=<npm-pack-output>` to serve the real poc_packages
   payload; `CLIENT=<bin>` to test a specific client version). For
   program-specific impact payloads, adapt `poc_packages/` (rename to
   the target name, authorized engagements only). Write it up under
   `triage/pocs/<org>-<package>/` with the chain, evidence, and caveats.

   npm tag → proof recipe (all verified on npm 11.19 AND 12.2):

   | Finding tag | Prove with | npm 12 result |
   |---|---|---|
   | `:runner` | `demo_npm_rce.sh <name> runner` — npx fetch-and-run | RCE |
   | `:dep` | `demo_npm_rce.sh <name> dep` — install then `require()` | RCE |
   | `:dev` / tool usage visible in victim scripts or CI | `demo_npm_rce.sh <name> tool` — victim's own `npm run` invokes the delivered bin | RCE |
   | install-script only (untagged, docs-instruction) | plain install on npm <12 or allowlisted client; on npm 12 default it is BLOCKED — claim legacy-client exposure or drop to hardening | blocked on 12+ |
6. **Report** — short and direct, no prose: summary, affected locations
   with permalinks, reproduction steps, impact (human AND AI-agent
   following the docs), remediation. Rank by: in-scope direct → policy
   text → chain → arguable; then docs exposure; then repo freshness.
   Stale (2y+) repos sink.

Work products live under `triage/` (gitignored): `TRIAGE_REPORT.md`,
`FALSE_POSITIVES.md`, `SCOPE_ANALYSIS.md`, `triage_data.json`, and
`triage/pocs/<org>-<package>/` per validated exploit chain.

## PoC rules (hard constraints)

1. NEVER publish/upload to npm, PyPI, RubyGems, or any real registry —
   not even "harmless" packages — unless the human owner explicitly
   decides to (benign, clearly-labeled placeholders only, identified with
   the researcher's handles, offered for transfer/removal).
2. No testing against live devices, services, or orgs. Everything runs
   against 127.0.0.1 and paths under /tmp or `triage/pocs/`.
3. Local simulation pattern: `python3 scripts/fake_registry.py` serves
   all three registries on localhost (any npm/PyPI name dynamically; gem
   names via --gem-name), logs every RESOLUTION, and delivers marker
   payloads. Install into throwaway prefixes only. Full instructions and
   registry-priority scenarios: poc_packages/README.md.
4. Ask before installing any tooling. Existing tooling: python3 stdlib,
   the local npm client, git clones of public repos.
5. `poc_packages/` (dns / placeholder / rce per registry) is the shared
   payload source: rename to the target name for authorized engagements,
   honor `POC_NO_AUTORUN`/`POC_IMPACT` semantics, and read its README for
   the per-registry execution-point differences before writing a report.
   Execution points: npm `preinstall`; PyPI sdist `setup.py` + import;
   RubyGems `extconf.rb` at install (runs during `gem install`) plus
   `require`.

## OpSec / disclosure hygiene

- Never commit research targets: `triage/`, results, scan logs, and PoC
  outputs are gitignored — keep it that way. Tests and committed docs use
  SYNTHETIC shape-classes instead of real finding names (see
  `tests/test_validate.py` for the pattern and the rationale).
- Placeholder reservations on registries are the owner's call, timed
  against the report submission, never automated.

## Changing the filters

`shark/validate.py` rules are corpus-tuned: 0 of 211 hand-verified valid
names rejected; ~43% of 759 false positives die at the name level, ~63%
including path/uv/shadow rules. If you change a rule:

1. update `tests/test_validate.py` shape cases to match the intended
   behavior,
2. state in the commit message that corpus behavior changed and why.

The extraction streams exclude `spec/ test/ tests/ fixtures/ testdata/
test-fixtures/ __tests__/` trees — the bundler/rubygems fixture corpora
were the single largest FP source. A repo literally named `tests/` gets
excluded too; that is accepted behavior.

## Tests

```
pytest                # hermetic suite (fake registries, no network)
pytest -m live        # 6 live smoke requests against real registries
```

The e2e test runs real ripgrep extraction over the in-repo fixture repo
(`tests/conftest.py`) with only the HTTP layer faked — keep it green
before any commit.

## npm exec paths & severity

MEASURED, not assumed. Sources: InfoQ npm-12 coverage (Aug 2026; allowScripts
default-off since npm 12.0, warned since 11.16) + empirical verification with
`scripts/fake_registry.py` (2026-10-14; npm 12.2.0 installed to a /tmp prefix
— never upgrade the system npm for this):

| Victim action | npm 11.19 | npm 12.2 |
|---|---|---|
| `npm install <pkg>` alone → dependency preinstall | RUNS (+ advisory warn) | **BLOCKED** (explicit warn; allowlist required) |
| bin linking into `node_modules/.bin` | yes | **yes** |
| `npx <pkg>` fetch-and-run (`:runner`) | RUNS | **RUNS** |
| import-time `require()` of installed dep (`:dep`) | RUNS | **RUNS** |
| victim's OWN package.json scripts invoking the linked bin (`npm run x`) | RUNS | **RUNS** (root scripts not gated; `.bin` on the npm-run PATH) |
| full `npm install` with victim postinstall invoking the delivered bin | RUNS | **RUNS — RCE DURING INSTALL** (root lifecycle scripts are not gated; nuance: root lifecycles fire on full installs, not `npm install <pkg>` additions) |
| `npm install -g <pkg>` → dependency preinstall | RUNS | BLOCKED (warn suggests `--allow-scripts` flag) |
| `npm install -g <pkg>` → bin + later invocation | RCE | **RCE on invocation** (global bin linked) |

Decision tree for the plain `npm install <x>` finding shape (docs/README
instructions — the most common finding):

1. What kind of name is it?
   - CLI tool (docs then tell you to RUN it, or install with `-g`):
     → `:runner`-equivalent flow. npm 12: RCE on first invocation.
       Proof: `demo_npm_rce.sh <x> global` (for -g docs) or `runner`.
   - Library (the repo imports it): → `:dep`. npm 12: RCE at import.
       Proof: `demo_npm_rce.sh <x> dep`.
   - Build/lint tool invoked in the victim's package.json `scripts` or
     CI: → tool flow. npm 12: RCE when their script runs (and DURING
     full installs if a lifecycle script calls it). Proof:
     `demo_npm_rce.sh <x> tool` and `ownscript`.
2. Client reality: `npm install <x>` alone no longer executes package
   code on npm 12+ — do not claim install-time RCE for the "alone" case
   without a legacy/allowlisted client. Claim delivery + first-use
   execution, scoped exactly as the table above.
3. Impact sentence template (npm 12 era): "Registering <x> delivers
   attacker code to every client that follows the instruction; it
   executes [on invocation | at import | via the repo's own scripts |
   during install where the repo's postinstall calls it] — verified
   against npm <tested-version> with a local fake registry. On npm <12
   clients it additionally executes at install time."

Re-verify on every new client release: run
`scripts/verify_npm_exec_paths.sh` (any client binary via `CLIENT=...`;
for future npm versions use `npm install --prefix /tmp/npmX npm@X` and
point CLIENT at `/tmp/npmX/node_modules/.bin/npm` — never touch the
system npm), then update the matrix above.

## Registry coverage decisions

**Terraform — validated 2026-10-14, not added.** The supply-chain confusion
class does exist for Terraform, with two variants:

- *Public registry (registry.terraform.io)*: real RCE-class vector — the
  module API is anonymously checkable (200/404) and victims fetch modules
  unauthenticated (the download handshake returns
  `X-Terraform-Get: git::https://github.com/<namespace>/...`, an anonymous
  git clone). BUT namespaces are bound to GitHub orgs (modules publish from
  GitHub repos), so squatting requires claiming the target's GitHub org —
  only possible for deleted/renamed orgs. Rare.
- *Private TFC (app.terraform.io)*: org names are claimable by signup, but
  org existence has NO unauthenticated check (401 for existing and missing
  orgs alike), and private-registry modules are org-scoped and
  auth-required — a victim's token cannot fetch an attacker org's module.
  Takeover is namespace occupation/DoS, not code execution.

Yield across a sampled subset of our scanned accounts was ~zero (11 orgs
sampled: one had 2 `app.terraform.io` refs; the findings corpus had 1
file). If we ever target infra-heavy accounts, revisit and implement only
the public-registry class.
