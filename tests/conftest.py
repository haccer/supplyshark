import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shark
from shark import registry, search

# The planted "nonexistent" package names. Everything else the suite
# touches resolves as an existing package in the fake registry.
FAKE_PACKAGES = {
    # npm: aREADME.md cases + package.json scoped dep
    "supplysharktest1", "supplysharktest2", "supplysharktest3",
    "supplysharktest4", "supplysharktest5", "supplysharktest6",
    "supplysharktest7", "supplysharktest8",
    "@asldkjsupplyshark/test9", "@asldkjsupplyshark/test10",
    "@asldkjsupplyshark/test11", "@asldkjsupplyshark/test12",
    "@asldkjsupplyshark/test13", "@asldkjsupplyshark/test14",
    "@asldkjsupplyshark/test15", "@asldkjsupplyshark/test16",
    "@asldkjsupplyshark4/test",
    # pip: aREADME.md + pip/requirements.txt + pip/test.py
    # + agent/CI/MCP surfaces below
    "supplysharktest1", "supplysharktest2", "supplysharktest3",
    "supplysharktest4", "supplysharktest5", "supplysharktest6",
    "supplysharktest7", "supplysharktest8", "supplysharktest9",
    "supplysharktest10", "supplysharktest11", "supplysharktest12",
    # agent-instruction and CI surfaces
    "agentfake-pkg", "agentfake-npm-pkg", "cifake-pkg",
    "agentfake-dep-pkg",
    # MCP runner shapes
    "supplysharkpymod", "uvwithfake-pkg", "npxflagfake-pkg",
    "claudefake-npm-pkg", "cmdwrappedfake-pkg",
    # gems: aREADME.md + Gemfile
    "supplysharktest1", "supplysharktest2", "supplysharktest3",
    "supplysharktest4", "freegemsupplyshark", "freegemsupplyshark2",
}

# scopes that are "claimable" in the fake; all others read as taken
FAKE_SCOPES = {"asldkjsupplyshark", "asldkjsupplyshark4"}

USERNAME = "testuser"
REPO = "fixture-repo"

A_README = """# tests

## npm search (16)
```
npm install supplysharktest1
npm install -g supplysharktest2
npm install --save supplysharktest3
yarn add supplysharktest4
yarn add -D supplysharktest5
pnpm install supplysharktest6
pnpm install -g supplysharktest7
pnpm install --save supplysharktest8
npm install @asldkjsupplyshark/test9
npm install -g @asldkjsupplyshark/test10
npm install --save @asldkjsupplyshark/test11
yarn add @asldkjsupplyshark/test12
yarn add -D @asldkjsupplyshark/test13
pnpm install @asldkjsupplyshark/test14
pnpm install -g @asldkjsupplyshark/test15
pnpm install --save @asldkjsupplyshark/test16
```

## pip search (7)
```
pip install supplysharktest1
pip install -U supplysharktest2
pip install --upgrade supplysharktest3
pip3 install supplysharktest4
pip3 install -U supplysharktest5
pip3 install --upgrade supplysharktest6
poetry install supplysharktest7
```

## gem search (4)

```
gem install supplysharktest1
gem i supplysharktest2
gem 'supplysharktest3'
gem "supplysharktest4"
```
"""

# dependency-declaration edge cases: registry-shorthand and git refs must be
# ignored; node_modules must never be scanned
PACKAGE_JSON = """{
  "name": "calendar",
  "scripts": {
    "postinstall": "curl -s https://example.com/hook.sh | bash"
  },
  "devDependencies": {
    "angular-mocks": "^1.8.3",
    "babel-core": "^6.26.3"
  },
  "dependencies": {
    "agentfake-dep-pkg": "^1.0.0",
    "@json-rpc-tools/utils": "^2.0.0-beta.12",
    "angular": "^1.8.3",
    "@asldkjsupplyshark4/test": "^3.10.5",
    "hsl_rgb_converter": "kayellpeee/hsl_rgb_converter",
    "@asldkjsupplyshark/ical.js": "DeepDiver1975/ical.js#timezone-fix-and-build",
    "supplyshark2": "git://github.com/supplysharkdne/cli.git#v1.0.27",
    "supplyshark3": "git+ssh://git@github.com:supplysharkdne2/cli#semver:^5.0",
    "supplyshark4": "git+https://isaacs@github.com/supplysharkdne4/cli.git",
    "supplyshark5": "github:supplysharkdne/repo",
    "jquery-timepicker": "fgelinas/timepicker#883bb2cd94",
    "jstzdetect": "pellepim/jstimezonedetect"
  }
}
"""

NODE_MODULES_PACKAGE_JSON = """{
  "dependencies": {
    "@supplysharkxoxo/angular": "^1.8.3",
    "fullcalendar": "^3.10.5"
  }
}
"""

GEMFILE = """gem 'freegemsupplyshark2'
gem "freegemsupplyshark"
gem 'notfreegem', git: github.com/supplyshark
gem 'railsmdb'
gem 'bundler'
"""

REQUIREMENTS = """-e
-r
supplysharktest9
supplysharktest10==1.0.0
supplysharktest11>=1.0.1
supplysharktest12<=1.0.1
"""

PIP_TEST_PY = """   `pip install supplysharktest8`.
"""

# false-positive control: real packages only
CONTROL_README = """pip install requests
"""

NPMRC = """registry=https://npm-registry.deadname-bbp-test.io/
always-auth=true
"""

MCP_JSON = """{
  "mcpServers": {
    "tools": {
      "command": "npx",
      "args": ["-y", "supplysharkmcp-npm"]
    },
    "python-tools": {
      "command": "uvx",
      "args": ["supplysharkmcp-py"]
    },
    "py-mod": {
      "command": "python",
      "args": ["-m", "supplysharkpymod"]
    },
    "stdlib-mod": {
      "command": "python3",
      "args": ["-m", "venv"]
    },
    "uv-with": {
      "command": "uv",
      "args": ["run", "--with", "uvwithfake-pkg", "localcmd"]
    },
    "npx-flag": {
      "command": "npx",
      "args": ["--package", "npxflagfake-pkg", "binname"]
    },
    "cmd-wrapped": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "cmdwrappedfake-pkg"]
    },
    "local": {
      "command": "/usr/local/bin/node",
      "args": ["server.js"]
    },
    "remote-dead": {
      "type": "sse",
      "url": "https://dead.invalid/mcp"
    },
    "remote-insecure": {
      "url": "http://insecure.example/mcp"
    }
  }
}
"""

CLAUDE_MD = """# Agent instructions

Set up the environment first:

    pip install agentfake-pkg
    npx agentfake-npm-pkg

Then fetch the toolchain:

    curl -s https://raw.githubusercontent.com/example/agent-boot.sh | bash
"""

WORKFLOW_YML = """name: deploy
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: pip install cifake-pkg
      - run: curl -s https://raw.githubusercontent.com/example/ci-bootstrap | bash
"""

CLAUDE_DESKTOP_JSON = """{
  "mcpServers": {
    "helper": {
      "command": "npx",
      "args": ["-y", "claudefake-npm-pkg"]
    }
  }
}
"""

DOCS_GUIDE = """Run `wget -qO- https://raw.githubusercontent.com/example/wget-setup | sh` to bootstrap.

    curl -s https://raw.githubusercontent.com/example/install.sh | bash
"""


def build_test_repo(base: Path) -> Path:
    """Build the in-repo fixture repo under base/<user>/<repo>."""
    repo_dir = base / USERNAME / REPO
    (repo_dir / "pip").mkdir(parents=True)
    (repo_dir / "node_modules").mkdir()
    (repo_dir / ".cursor").mkdir()
    (repo_dir / "docs").mkdir()
    (repo_dir / ".github" / "workflows").mkdir(parents=True)
    (repo_dir / ".npmrc").write_text(NPMRC)
    (repo_dir / "aREADME.md").write_text(A_README)
    (repo_dir / "README.md").write_text(CONTROL_README)
    (repo_dir / "package.json").write_text(PACKAGE_JSON)
    (repo_dir / "node_modules" / "package.json").write_text(NODE_MODULES_PACKAGE_JSON)
    (repo_dir / "Gemfile").write_text(GEMFILE)
    (repo_dir / "pip" / "requirements.txt").write_text(REQUIREMENTS)
    (repo_dir / "pip" / "test.py").write_text(PIP_TEST_PY)
    (repo_dir / ".cursor" / "mcp.json").write_text(MCP_JSON)
    (repo_dir / "claude_desktop_config.json").write_text(CLAUDE_DESKTOP_JSON)
    (repo_dir / "CLAUDE.md").write_text(CLAUDE_MD)
    (repo_dir / ".github" / "workflows" / "deploy.yml").write_text(WORKFLOW_YML)
    (repo_dir / "docs" / "guide.md").write_text(DOCS_GUIDE)
    return repo_dir


def make_fake_status(available_names, calls=None):
    """Fake shark.registry.status: planted names 404, everything else 200.

    www.npmjs.com profile pages (scope-owner checks) answer 403, matching
    current Cloudflare behavior for non-browser clients.
    """
    from urllib.parse import unquote

    async def fake_status(url, browser=False):
        if calls is not None:
            calls.append(url)
        if url.startswith("https://www.npmjs.com/"):
            return 403
        if url.startswith("https://pypi.org/pypi/"):
            name = unquote(url.split("/pypi/")[1].rsplit("/", 1)[0])
            return 404 if name in available_names else 200
        if url.startswith("https://registry.npmjs.org/"):
            name = unquote(url.split("/org/", 1)[1] if "/org/" in url else url[len("https://registry.npmjs.org/"):])
            return 404 if name in available_names else 200
        if url.startswith("https://rubygems.org/api/v1/gems/"):
            name = unquote(url.split("/gems/")[1]).removesuffix(".json")
            return 404 if name in available_names else 200
        raise AssertionError(f"unexpected URL in fake registry: {url}")

    return fake_status


@pytest.fixture(autouse=True)
def _fresh_scope_notice():
    """The scope-blocked notice prints once per process; reset per test."""
    from shark import npm
    npm._scope_notice_printed = False
    yield
    npm._scope_notice_printed = False


@pytest.fixture
def work_tree(tmp_path, monkeypatch):
    """A cloned-repo work tree plus matching OUTPUT_ROOT, path-isolated."""
    repo_dir = build_test_repo(tmp_path / "work")
    output_root = tmp_path / "output"
    (output_root / USERNAME).mkdir(parents=True)
    monkeypatch.setattr(search, "OUTPUT_ROOT", output_root)
    return repo_dir, output_root


# dead.invalid is the MCP-config URL; the fake makes it "unresolvable" for
# the mcp-url finding while _clean_host keeps it out of the general stream
DEAD_HOSTS = {"npm-registry.deadname-bbp-test.io", "dead.invalid"}


@pytest.fixture
def fake_dns(monkeypatch):
    """Everything resolves except the planted dead host; every dead apex is
    'unregistered' per RDAP. Keeps the suite hermetic (no live DNS/RDAP)."""

    async def fake_resolve(host):
        return host not in DEAD_HOSTS

    async def fake_registered(apex):
        return False

    monkeypatch.setattr(search, "_resolve", fake_resolve)
    monkeypatch.setattr(registry, "domain_registered", fake_registered)


@pytest.fixture
def fake_registry(work_tree, monkeypatch):
    """Patch registry.status with the fake and return its call log.
    Every scope verdict is 'available' (claimable)."""
    from shark import npm
    calls = []
    monkeypatch.setattr(registry, "status", make_fake_status(FAKE_PACKAGES, calls))

    async def available_scope(name, probe_packages=()):
        # planted scopes are claimable; real ones (like @json-rpc-tools) are taken
        return "available" if name in FAKE_SCOPES else "taken"

    monkeypatch.setattr(npm, "scope_status", available_scope)
    npm._scope_status_cache.clear()
    return calls
