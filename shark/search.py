from . import registry
import aiofiles
import asyncio
import tldextract
import pathlib
import json
import shlex
import subprocess
import re
from urllib.parse import urlparse

# Clone/output locations. Overridable (e.g. by tests) so the pipeline does
# not depend on /tmp specifically.
OUTPUT_ROOT = pathlib.Path("/tmp/.supplyshark/_output")

def _clone_file_ref(file_path, scan_root, username):
    """File reference in '<user>/<repo>/path' form. scan_root is the repo
    clone directory, so its name is the repo segment."""
    root = pathlib.Path(scan_root).resolve()
    rel = pathlib.Path(file_path).resolve().relative_to(root)
    return f"{username}/{root.name}/{rel.as_posix()}"

def _output_file_ref(file_path, scan_root):
    """File reference relative to OUTPUT_ROOT: '<user>/<repo>/path'.
    scan_root is OUTPUT_ROOT/<user>, so its name is the user prefix."""
    rel = pathlib.Path(file_path).resolve().relative_to(pathlib.Path(scan_root).resolve())
    return f"{pathlib.Path(scan_root).resolve().name}/{rel.as_posix()}"

def get_packages(path, username, repo):
    func_args_list = [
        (npm_install_files, (path, username)),
        (pip_install_files, (path, username)),
        (gem_install_files, (path, username)),
        (mcp_config_files, (path, username)),
        (find_urls, (path, username)),
        (copy_files, (path, username, repo, 'package.json')),
        (copy_files, (path, username, repo, 'Gemfile')),
        (copy_files, (path, username, repo, 'requirements.txt')),
        (copy_files, (path, username, repo, '*requirements*.txt')),
        (copy_files, (path, username, repo, 'pyproject.toml')),
        (copy_files, (path, username, repo, '.npmrc')),
    ]

    for func, args in func_args_list:
        func(*args)

def _append_matches(output_file, lines):
    with open(output_file, 'a') as f:
        for item in lines:
            f.write(json.dumps(item) + '\n')

def _clean_host(raw: str) -> str | None:
    """Normalize an rg-captured URL authority into a bare hostname, or None
    if it isn't a plausible public DNS name."""
    strip_chars = ".,;:)]>'" + '"' + "`"
    host = raw.strip().strip(strip_chars)
    if "@" in host:
        host = host.split("@")[-1]  # drop userinfo
    if host.startswith("["):
        return None  # IPv6 literal
    host = host.split(":")[0].lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+", host):
        return None
    if re.fullmatch(r"([0-9]{1,3}\.){3}[0-9]{1,3}", host):
        return None  # IPv4 literal
    labels = host.split(".")
    tld = labels[-1]
    if len(labels) < 2 or tld in ("local", "internal", "example", "invalid", "test", "localhost"):
        return None
    if host in ("localhost", "127.0.0.1") or host.startswith("127."):
        return None

    # documentation placeholders are never real hosts
    if host in PLACEHOLDER_HOSTS or host.endswith((".example.com", ".example.org", ".example.net")):
        return None
    first = labels[0]
    if first.startswith("your"):
        return None
    if len(labels) == 2 and first.split("-")[0] in (
            "my", "test", "demo", "sample", "example", "placeholder", "foo", "bar", "baz", "ekzample"):
        return None
    if any(label in PLACEHOLDER_LABELS or label.startswith("example-") for label in labels):
        return None

    # docs junk with invented TLDs (foo.chain, a.b, target.whatever): the
    # Public Suffix List doesn't know the TLD, so there is no registrable
    # domain and nothing to take over
    if not _registrable_apex(host):
        return None

    return host


# bundled snapshot only: deterministic and offline-safe; snapshot ages but
# is fine for validity/apex purposes
_DOMAIN_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())


def _registrable_apex(host: str) -> str:
    """Registrable domain per the Public Suffix List (empty if the host's
    TLD isn't a real public suffix, e.g. docs junk like foo.chain)."""
    result = _DOMAIN_EXTRACTOR(host)
    if result.domain and result.suffix:
        return f"{result.domain}.{result.suffix}"
    return ""


PLACEHOLDER_HOSTS = {
    "test.com", "domain.com", "example.com", "example.org", "example.net",
    "yourdomain.com", "your-domain.com", "foo.com", "bar.com", "baz.com",
    "url.com", "website.com", "mysite.com", "domain.tld",
}

# placeholder vocabulary appearing as any DNS label (my.specific-domain.com)
PLACEHOLDER_LABELS = {
    "your-domain", "yourdomain", "specific-domain", "my-domain",
    "example-domain", "test-domain", "domain-name", "your-app", "yourapp",
    "yourcompany", "your-company", "ekzample",
}

def find_urls(path, username):
    """Collect every hostname referenced by an http(s) URL in the tree —
    configs (.npmrc, pip.conf, renovate.json), docs, scripts — for
    dead-domain takeover checks at scan time."""
    # capture group + -r avoids lookbehind: stock ripgrep has no PCRE2
    command = (f"rg --hidden -g '!.git' -g '!**/node_modules/**' "
               f"-o -r '$1' 'https?:\\/\\/([^\\/&\\s\"<>{{}}]+)' --no-heading -n {path}")
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/urls_search.json"

    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()

    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()

            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break

            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            raw = line.split(":", 2)[2].replace('\n', '')

            host = _clean_host(raw)
            if host is None or "node_modules" in file_path:
                continue

            f.write(json.dumps({
                "file": _clone_file_ref(file_path, path, username),
                "line_number": line_number,
                "match": host
            }) + '\n')

def npm_install_files(path, username):
    # npx/bunx/pnpm dlx/yarn dlx execute packages straight off the registry;
    # they appear in READMEs and agent configs alike.
    command = f"rg --hidden -g '!.git' -g '!**/node_modules/**' -g '!**/spec/**' -g '!**/test/**' -g '!**/tests/**' -g '!**/fixtures/**' -g '!**/testdata/**' -g '!**/test-fixtures/**' -g '!**/__tests__/**' -e 'yarn add|yarn dlx|npm install|npm i |npm ci|pnpm install|pnpm add|pnpm dlx|npx |bun add|bunx ' -g '!*yarn-error.log' --no-heading -g '!*/node_modules' -n {path}"
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/npm_search.json"
    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    bad_paths = ['node_modules']

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()
            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break
            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            match = line.split(":", 2)[2]
            if not any(bad_path in file_path for bad_path in bad_paths):
                f.write(json.dumps({
                    "file": _clone_file_ref(file_path, path, username),
                    "line_number": line_number,
                    "match": match.replace('\n', '')
                }) + '\n')

def pip_install_files(path, username):
    command = f"rg --hidden -g '!.git' -g '!**/node_modules/**' -g '!**/spec/**' -g '!**/test/**' -g '!**/tests/**' -g '!**/fixtures/**' -g '!**/testdata/**' -g '!**/test-fixtures/**' -g '!**/__tests__/**' -e 'pip install|pip3 install|poetry install|poetry add|pipx install|uv add|uv pip install|uvx |uv tool install' --no-heading -g '!*/node_modules' -n {path}"
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/pip_search.json"
    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()
            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break
            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            match = line.split(":", 2)[2]
            f.write(json.dumps({
                "file": _clone_file_ref(file_path, path, username),
                "line_number": line_number,
                "match": match.replace('\n', '')
            }) + '\n')

def gem_install_files(path, username):
    command = (f'rg --hidden -g "!.git" -g "!**/node_modules/**" '
             f'-g "!**/spec/**" -g "!**/test/**" -g "!**/tests/**" '
             f'-g "!**/fixtures/**" -g "!**/testdata/**" -g "!**/test-fixtures/**" '
             f'-g "!**/__tests__/**" "gem i |gem \'|gem install|gem \\\"" --no-heading '
             f'-g "!*/node_modules" -n {path}')
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/gem_search.json"
    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    bad_values = ['install ./',
                 ':git',
                 'install --dev ./']

    bad_paths = ['node_modules']

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()
            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break
            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            match = line.split(":", 2)[2]
            if not any(bad_value in line for bad_value in bad_values):
                if not any(bad_path in file_path for bad_path in bad_paths):
                    f.write(json.dumps({
                        "file": _clone_file_ref(file_path, path, username),
                        "line_number": line_number,
                        "match": match.replace('\n', '')
                    }) + '\n')

PLACEHOLDER_HOSTS = {
    "test.com", "domain.com", "example.com", "example.org", "example.net",
    "yourdomain.com", "your-domain.com", "foo.com", "bar.com", "baz.com",
    "url.com", "website.com", "mysite.com", "domain.tld",
}

# placeholder vocabulary appearing as any DNS label (my.specific-domain.com)
PLACEHOLDER_LABELS = {
    "your-domain", "yourdomain", "specific-domain", "my-domain",
    "example-domain", "test-domain", "domain-name", "your-app", "yourapp",
    "yourcompany", "your-company", "ekzample",
}

def find_urls(path, username):
    """Collect every hostname referenced by an http(s) URL in the tree —
    configs (.npmrc, pip.conf, renovate.json), docs, scripts — for
    dead-domain takeover checks at scan time."""
    # capture group + -r avoids lookbehind: stock ripgrep has no PCRE2
    command = (f"rg --hidden -g '!.git' -g '!**/node_modules/**' "
               f"-o -r '$1' 'https?:\\/\\/([^\\/&\\s\"<>{{}}]+)' --no-heading -n {path}")
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/urls_search.json"

    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()

    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()

            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break

            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            raw = line.split(":", 2)[2].replace('\n', '')

            host = _clean_host(raw)
            if host is None or "node_modules" in file_path:
                continue

            f.write(json.dumps({
                "file": _clone_file_ref(file_path, path, username),
                "line_number": line_number,
                "match": host
            }) + '\n')

def npm_install_files(path, username):
    # npx/bunx/pnpm dlx/yarn dlx execute packages straight off the registry;
    # they appear in READMEs and agent configs alike.
    command = f"rg --hidden -g '!.git' -g '!**/node_modules/**' -g '!**/spec/**' -g '!**/test/**' -g '!**/tests/**' -g '!**/fixtures/**' -g '!**/testdata/**' -g '!**/test-fixtures/**' -g '!**/__tests__/**' -e 'yarn add|yarn dlx|npm install|npm i |npm ci|pnpm install|pnpm add|pnpm dlx|npx |bun add|bunx ' -g '!*yarn-error.log' --no-heading -g '!*/node_modules' -n {path}"
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/npm_search.json"
    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    bad_paths = ['node_modules']

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()
            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break
            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            match = line.split(":", 2)[2]
            if not any(bad_path in file_path for bad_path in bad_paths):
                f.write(json.dumps({
                    "file": _clone_file_ref(file_path, path, username),
                    "line_number": line_number,
                    "match": match.replace('\n', '')
                }) + '\n')

def pip_install_files(path, username):
    command = f"rg --hidden -g '!.git' -g '!**/node_modules/**' -g '!**/spec/**' -g '!**/test/**' -g '!**/tests/**' -g '!**/fixtures/**' -g '!**/testdata/**' -g '!**/test-fixtures/**' -g '!**/__tests__/**' -e 'pip install|pip3 install|poetry install|poetry add|pipx install|uv add|uv pip install|uvx |uv tool install' --no-heading -g '!*/node_modules' -n {path}"
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/pip_search.json"
    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()
            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break
            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            match = line.split(":", 2)[2]
            f.write(json.dumps({
                "file": _clone_file_ref(file_path, path, username),
                "line_number": line_number,
                "match": match.replace('\n', '')
            }) + '\n')

def gem_install_files(path, username):
    command = (f'rg --hidden -g "!.git" -g "!**/node_modules/**" '
             f'-g "!**/spec/**" -g "!**/test/**" -g "!**/tests/**" '
             f'-g "!**/fixtures/**" -g "!**/testdata/**" -g "!**/test-fixtures/**" '
             f'-g "!**/__tests__/**" "gem i |gem \'|gem install|gem \\\"" --no-heading '
             f'-g "!*/node_modules" -n {path}')
    output_path = OUTPUT_ROOT / username
    output_file = f"{output_path}/gem_search.json"
    if not pathlib.Path(output_file).exists():
        pathlib.Path(output_file).touch()
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)

    bad_values = ['install ./',
                 ':git',
                 'install --dev ./']

    bad_paths = ['node_modules']

    with open(output_file, 'a') as f:
        while True:
            line = process.stdout.readline()
            if line == b'':
                process.wait()  # reap rg; zombies exhaust maxproc on large orgs
                break
            line = line.decode('utf-8')
            file_path = line.split(":")[0]
            line_number = line.split(":")[1]
            match = line.split(":", 2)[2]
            if not any(bad_value in line for bad_value in bad_values):
                if not any(bad_path in file_path for bad_path in bad_paths):
                    f.write(json.dumps({
                        "file": _clone_file_ref(file_path, path, username),
                        "line_number": line_number,
                        "match": match.replace('\n', '')
                    }) + '\n')

# runner commands that fetch packages from a public registry; these are what
# AI agents (MCP clients, coding assistants) execute at startup
RUNNER_REGISTRY = {
    'npx': 'npm',
    'bunx': 'npm',
    'uvx': 'pip',
    'pipx': 'pip',
    'uv': 'pip',
    'python': 'pip',
    'python3': 'pip',
}

# flags whose following value names a package (--with dep, --package pkg, ...)
PACKAGE_FLAGS = {'-p', '--package', '--with', '-w', '--from'}

# stdlib modules that must never be reported as missing PyPI packages when
# they appear as `python -m <module>` in agent configs
PY_STDLIB_MODULES = {
    'abc', 'argparse', 'asyncio', 'base64', 'build', 'bz2', 'codecs',
    'compileall', 'configparser', 'contextlib', 'ctypes', 'decimal',
    'difflib', 'email', 'enum', 'fileinput', 'functools', 'gettext',
    'gzip', 'hashlib', 'heapq', 'hmac', 'http', 'idlelib', 'importlib',
    'inspect', 'io', 'ipaddress', 'itertools', 'json', 'logging',
    'multiprocessing', 'numbers', 'pathlib', 'pdb', 'platform', 'pprint',
    'queue', 'random', 're', 'secrets', 'select', 'shlex', 'shutil',
    'signal', 'site', 'socket', 'sqlite3', 'ssl', 'statistics', 'string',
    'struct', 'subprocess', 'sysconfig', 'tarfile', 'tempfile', 'textwrap',
    'threading', 'timeit', 'tokenize', 'trace', 'traceback', 'typing',
    'unittest', 'urllib', 'uuid', 'venv', 'warnings', 'wave', 'weakref',
    'xml', 'zipapp', 'zipfile', 'zlib',
}

# Windows wrappers: cmd /c npx ... or C:\...\npx.cmd
CMD_WRAPPERS = {'cmd', 'cmd.exe'}


# canonical match strings for the search streams; each is a command form the
# package extractor understands and that names the registry it pulls from
CANONICAL_MATCH = {
    'npx': 'npx {}',
    'bunx': 'bunx {}',
    'uvx': 'uvx {}',
    'uv': 'uvx {}',          # uv tool run / uv run --with pull from PyPI like uvx
    'pipx': 'pipx install {}',
    'python': 'pip install {}',
    'python3': 'pip install {}',
}


def _runner_base(command: str) -> str:
    """Normalize a command path to its runner name (npx.cmd -> npx)."""
    base = command.replace('\\', '/').split('/')[-1].lower()
    for suffix in ('.cmd', '.exe', '.bat'):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    return base


def _extract_runner_packages(base: str, args) -> list:
    """Package names referenced by a runner invocation, per command shape:

    npx|bunx [-y] pkg            -> pkg
    npx --package pkg cmd        -> pkg (the command comes from pkg)
    uvx [--from dist] tool       -> dist, tool
    uv run [--with dep] cmd      -> dep only (cmd is usually local)
    uv tool run pkg              -> pkg
    pipx [install|run] pkg       -> pkg
    python -m module             -> module (unless stdlib)
    """
    str_args = [a for a in args if isinstance(a, str)]
    packages = []

    flag_values = []
    positional = []
    i = 0
    while i < len(str_args):
        arg = str_args[i]
        if arg.startswith('--package='):
            flag_values.append(arg[len('--package='):])
            i += 1
            continue
        if arg in PACKAGE_FLAGS and i + 1 < len(str_args):
            flag_values.append(str_args[i + 1])
            i += 2
            continue
        if arg.startswith('-'):
            i += 1
            continue
        positional.append(arg)
        i += 1

    if base in ('npx', 'bunx'):
        # with an explicit --package the first positional is a binary inside it
        packages = flag_values or positional[:1]
    elif base == 'uvx':
        packages = flag_values + positional[:1]
    elif base == 'uv':
        lead = [a for a in str_args if not a.startswith('-')][:2]
        if 'tool' in lead:
            packages = flag_values + [a for a in positional if a not in ('tool', 'run', 'install')][:1]
        elif 'run' in lead:
            packages = flag_values  # uv run <local command>
    elif base == 'pipx':
        packages = [a for a in positional if a not in ('install', 'run', 'upgrade', 'inject')][:1]
    elif base in ('python', 'python3'):
        if '-m' in str_args:
            idx = str_args.index('-m')
            if idx + 1 < len(str_args):
                module = str_args[idx + 1]
                if '.' not in module and module not in PY_STDLIB_MODULES:
                    packages = [module]

    return [p for p in packages if p and not p.startswith('-')]


def mcp_config_files(path, username):
    """Extract registry packages and remote URLs from MCP/agent config files.

    These configs are consumed by AI agents (Claude Desktop, Claude Code,
    Cursor, Cline, Gemini CLI, ...). A server entry like {"command": "npx",
    "args": ["-y", "pkg"]} makes the agent fetch pkg from npm at startup, so
    a missing package name here is a live dependency-confusion target.
    Packages are appended to the same npm/pip search streams so downstream
    scanning treats them like any other referenced package; remote server
    URLs go to mcp_url_search.json for takeover/insecurity checks.
    """
    output_path = OUTPUT_ROOT / username
    root = pathlib.Path(path)

    candidates = []
    for file in root.rglob('*.json'):
        lowered = file.name.lower()
        config_dir = file.parent.name.lower()
        if ('mcp' in lowered
                or lowered == 'claude_desktop_config.json'
                or (config_dir in ('.gemini', '.continue', '.windsurf', '.trae') and lowered.endswith('.json'))):
            candidates.append(file)

    npm_lines = []
    pip_lines = []
    url_lines = []

    for file in candidates:
        try:
            text = file.read_text(encoding='utf-8', errors='ignore')
            data = json.loads(text)
        except Exception:
            continue

        servers = data.get('mcpServers') or data.get('mcp_servers') or {}
        if not isinstance(servers, dict):
            continue

        rel_path = _clone_file_ref(file, path, username)

        for server_name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue

            line_number = text[:text.find(f'"{server_name}"')].count('\n') + 1 if f'"{server_name}"' in text else 1

            url = cfg.get('url') or cfg.get('serverUrl') or cfg.get('sse')
            if isinstance(url, str) and url.startswith('http'):
                url_lines.append({"file": rel_path, "line_number": line_number, "match": url})
                continue

            command = cfg.get('command')
            args = cfg.get('args') or []
            if not isinstance(command, str) or not isinstance(args, list):
                continue

            base = _runner_base(command)
            if base in CMD_WRAPPERS and '/c' in [a for a in args if isinstance(a, str)]:
                rest = args[[i for i, a in enumerate(args) if a == '/c'][-1] + 1:]
                if rest and isinstance(rest[0], str):
                    base = _runner_base(rest[0])
                    args = rest[1:]

            registry_kind = RUNNER_REGISTRY.get(base)
            if registry_kind is None:
                continue

            packages = _extract_runner_packages(base, args)
            for package in packages:
                match = CANONICAL_MATCH[base].format(package)
                entry = {"file": rel_path, "line_number": line_number, "match": match}
                (npm_lines if registry_kind == 'npm' else pip_lines).append(entry)

    if npm_lines:
        _append_matches(f"{output_path}/npm_search.json", npm_lines)
    if pip_lines:
        _append_matches(f"{output_path}/pip_search.json", pip_lines)
    if url_lines:
        _append_matches(f"{output_path}/mcp_url_search.json", url_lines)


async def _resolve(host: str) -> bool:
    """True if the hostname resolves; wrapped for testability.
    Retries once because transient resolver failures under lookup floods
    would otherwise read as dead domains."""
    loop = asyncio.get_running_loop()
    for attempt in range(2):
        try:
            await asyncio.wait_for(loop.getaddrinfo(host, 443), timeout=10)
            return True
        except Exception:
            if attempt == 0:
                await asyncio.sleep(0.5)
    return False


# if none of these resolve, the local resolver is broken/offline and every
# dead-domain answer would be a false positive
CANARY_HOSTS = ("github.com", "registry.npmjs.org")


async def url_findings(copy_dir, concurrency: int = 25) -> list:
    """Dead-domain findings from every hostname the repos reference.

    An unresolvable domain in a repo means one of two things, both
    reportable: an internal-only hostname leaked publicly, or a domain
    that expired and can be re-registered — and re-registration captures
    everything that still points at it (install scripts, registries,
    webhooks, agent configs). Hosts already covered by MCP server URL
    findings are skipped to avoid duplicates.
    """
    for canary in CANARY_HOSTS:
        if await _resolve(canary):
            break
    else:
        print("[!] DNS resolver unreachable (canary hosts fail) — skipping dead-domain checks.")
        return []

    items = read_matches(f"{copy_dir}/urls_search.json")

    mcp_hosts = set()
    for item in read_matches(f"{copy_dir}/mcp_url_search.json"):
        host = urlparse(item["match"]).hostname
        if host:
            mcp_hosts.add(host.lower())

    by_host = {}
    for item in items:
        if item["match"] in mcp_hosts:
            continue
        by_host.setdefault(item["match"], []).append(item)

    semaphore = asyncio.Semaphore(concurrency)
    total = len(by_host)
    print(f"[*] Dead-domain check: resolving {total} unique hostname(s)...")
    progress = {"done": 0}

    async def check(host):
        async with semaphore:
            result = host, await _resolve(host)
            progress["done"] += 1
            if total > 25 and progress["done"] % 50 == 0:
                print(f"[*]   dead-domain progress: {progress['done']}/{total}")
            return result

    results = await asyncio.gather(*[check(host) for host in by_host])

    findings = []
    for host, resolves in results:
        if resolves:
            continue

        # only claimable domains are findings: the registrable apex must
        # itself be dead AND unregistered (RDAP 404). Dead subdomains under
        # a live apex (internal leaks, stale www links) and registered-but-
        # undelegated domains have nothing to take over.
        apex = _registrable_apex(host)
        if apex != host and await _resolve(apex):
            continue  # apex alive: not claimable
        registered = await registry.domain_registered(apex)
        if registered is True:
            continue  # registered but dead DNS: not claimable
        reason = "unregistered-domain" if registered is False else "unresolvable-domain"

        refs = by_host[host]
        findings.append([{"host": host, "reason": reason}] + [[ref] for ref in refs])

    return findings


async def mcp_url_findings(copy_dir) -> list:
    """Turn collected MCP server URLs into takeover findings: the endpoint's
    domain must no longer resolve AND be unregistered — whoever registers it
    owns the agent's MCP connection. Dotless/localhost hosts are machine-local
    and skipped; plaintext HTTP alone is a hygiene issue, not a takeover."""
    items = read_matches(f"{copy_dir}/mcp_url_search.json")
    by_url = {}
    for item in items:
        by_url.setdefault(item["match"], []).append(item)

    if by_url:
        print(f"[*] MCP endpoint check: {len(by_url)} unique url(s)...")

    async def classify(item):
        url, refs = item
        # takeover-only: the endpoint's domain must be claimable; plaintext
        # HTTP and other hygiene issues are not takeover findings
        host = urlparse(url).hostname or ""
        if not (host and "." in host and not host.endswith(".local")
                and host not in ("localhost", "127.0.0.1") and not host.startswith("127.")):
            return None
        if await _resolve(host):
            return None
        registered = await registry.domain_registered(_registrable_apex(host))
        if registered is True:
            return None  # registered but dead DNS: not claimable
        reason = "unregistered-domain" if registered is False else "unresolvable-domain"
        return [{"url": url, "reason": reason}] + [[ref] for ref in refs]

    classified = await asyncio.gather(*[classify(item) for item in by_url.items()])
    return [finding for finding in classified if finding]


def read_matches(path):
    """Read a *_search.json stream into its raw item dicts."""
    items = []
    file = pathlib.Path(path)
    if not file.exists():
        return items
    with open(file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                items.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return items

def copy_files(path, username, repo, filename):
    file_paths = []
    dest_dir = OUTPUT_ROOT / username / repo

    bad_paths = ["vendor/bundle/ruby/",
                "node_modules",
                "doc/requirements.txt",
                "jspm_packages"]

    for root in pathlib.Path(path).rglob(filename):
        if not any(bad_path in str(root) for bad_path in bad_paths):
            file_paths.append(root)

    for file_path in file_paths:
        source_file = file_path.relative_to(path)
        dest_file = dest_dir / source_file

        dest_dir_path = dest_file.parent
        if not dest_dir_path.exists():
            dest_dir_path.mkdir(parents=True)

        try:
            with open(file_path, 'rb') as input_file, open(dest_file, 'wb') as output_file:
                data = input_file.read()
                output_file.write(data)
        except:
            print("[!] Invalid file for copying. Skipping.")
            pass

async def package_json_results(path, value):
    command = f"rg --hidden -tjson -g package.json -F '{value}' --no-heading -n {path}"
    process = await asyncio.create_subprocess_exec(*shlex.split(command),
                                                  stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE)

    badvalues = [': "workspace:',
                ': "file:',
                ': "npm:',
                ': "git+',
                ': "github:',
                ': "https://github',
                ': "./',
                ': "git://',
                ': "/',
                ': "link:']

    results = []
    while True:
        line = await process.stdout.readline()
        if line == b'':
            await process.wait()  # reap rg
            break
        line = line.decode('utf-8')
        file_path = line.split(":")[0]
        line_number = line.split(":")[1]
        if re.search(rf'"{re.escape(value)}.*":', line) and not any(badvalue in line for badvalue in badvalues):
            results.append([{"file": _output_file_ref(file_path, path), "line_number": line_number, "value": value}])

    return json.dumps(results)

async def dependency_file_results(path, value, *rg_glob_args):
    """Find references to a value inside declared-dependency files
    (requirements*.txt, pyproject.toml) for citing in findings."""
    command = f"rg --hidden -F '{value}' --no-heading -n {' '.join(rg_glob_args)} {path}"
    process = await asyncio.create_subprocess_exec(*shlex.split(command),
                                                  stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE)
    results = []
    while True:
        line = await process.stdout.readline()
        if line == b'':
            await process.wait()  # reap rg
            break
        line = line.decode('utf-8')
        file_path = line.split(":")[0]
        line_number = line.split(":")[1]
        results.append([{"file": _output_file_ref(file_path, path), "line_number": line_number, "value": value}])

    return json.dumps(results)

async def package_search_json_results(path, value):
    matches = []
    if not pathlib.Path(path).exists():
        return matches
    boundary = re.compile(rf'(^|[^0-9A-Za-z._@/-]){re.escape(value)}($|[^0-9A-Za-z._-])')
    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
        async for line in f:
            try:
                item = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if boundary.search(item['match']):
                matches.append([item])

    return matches
