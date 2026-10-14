"""Package-name validation: registry grammars plus junk rules.

Applied at extraction time and again at scan entry, so malformed,
placeholder, and prose-extracted names never cost a registry request and
never reach results.txt.

Rules were tuned against a hand-triaged corpus of 970 findings from a
real sweep: 0 of 211 valid names are rejected; 323 of 759 false-positive
names are (43%). tests/test_validate.py replays that corpus as a
regression fixture, so loosening/tightening these rules is a visible,
test-enforced decision.
"""
import re

# npm: new-package rules — lowercase, URL-safe, no leading dot/underscore;
# scoped form is @scope/name with the scope in npm's username grammar
NPM_UNSCOPED = re.compile(r'^[a-z0-9](?:[a-z0-9._-]*[a-z0-9_])?$')
NPM_SCOPED = re.compile(r'^@[a-z0-9-]+/[a-z0-9](?:[a-z0-9._-]*[a-z0-9_])?$')
NPM_SCOPE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')

# PyPI (PEP 503 shape; pip normalizes -_. but the spelling must still parse)
PYPI = re.compile(r'^[A-Z0-9](?:[A-Z0-9._-]*[A-Z0-9])?$', re.IGNORECASE)

# RubyGems
GEM = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$')

VERSION_STRING = re.compile(r'^v?\d+(?:\.\d+)+[a-z0-9._-]*$', re.IGNORECASE)
NUMERIC = re.compile(r'^\d[\d.]*$')

# words lifted out of prose/echo text/comments by the extractor — every one
# of these was a real false positive in the triage corpus
STOPWORDS = {
    'from', 'for', 'error', 'failed', 'the', 'and', 'with', 'this', 'that',
    'requirements', 'docs', 'client', 'git', 'python', 'python3', 'binaries',
    'needed', 'recommended', 'installation', 'writes', 'capabilities',
    'ended', 'finished', 'locations', 'failing', 'invocation', 'entry',
    'previously', 'does-not-exist', 'any-required-dependencies', 'path',
    'command', 'semantics', 'cache', 'sission', 'dependecies', 'tis',
    'uvvx', 'https', 'http', 'www', 'com', 'org',
}

# tutorial/example vocabulary (mirror of PLACEHOLDER_HOSTS for packages);
# kept deliberately narrow so real names like pkg-release survive
PLACEHOLDER_PREFIX = re.compile(
    r'^(?:your|my|our|some|example|sample|demo|test|fake|dummy|placeholder)[-_]',
    re.IGNORECASE)

# metasyntactic names used by fixture suites (bundler specs alone produced
# qux/garply/waldo findings in the corpus)
METASYNTACTIC = {
    'foo', 'bar', 'baz', 'qux', 'quux', 'corge', 'grault', 'garply',
    'waldo', 'fred', 'plugh', 'xyzzy', 'toto', 'asdf', 'qwerty',
}

# npm blocks new publishes of node core-module names
NODE_CORE_MODULES = {
    'assert', 'async_hooks', 'buffer', 'child_process', 'cluster', 'console',
    'constants', 'crypto', 'dgram', 'diagnostics_channel', 'dns', 'domain',
    'events', 'fs', 'http', 'http2', 'https', 'inspector', 'module', 'net',
    'os', 'path', 'perf_hooks', 'process', 'punycode', 'querystring',
    'readline', 'repl', 'stream', 'string_decoder', 'sys', 'timers', 'tls',
    'trace_events', 'tty', 'url', 'util', 'v8', 'vm', 'wasi',
    'worker_threads', 'zlib', 'node',
}

# ${{ github.expr }} and ${var} — CI interpolation and shell templates that
# otherwise weld themselves onto extracted names (hiredis${{inputs.version)
TEMPLATE_VARS = re.compile(r'\$\{+[^}]*\}*')


def strip_template_vars(line: str) -> str:
    """Remove ${{ ... }} / ${...} interpolation before name extraction."""
    return TEMPLATE_VARS.sub('', line)


def is_junk_name(name: str) -> bool:
    """Registry-independent junk rules: empty, version strings, pure
    numerics, stopwords, metasyntactic names, placeholder prefixes."""
    if not name:
        return True
    if len(name) > 214:
        return True
    if VERSION_STRING.match(name) or NUMERIC.match(name):
        return True
    low = name.lower()
    if low in STOPWORDS or low in METASYNTACTIC:
        return True
    if PLACEHOLDER_PREFIX.match(name):
        return True
    return False


def valid_package(registry: str, name: str) -> bool:
    """Full validation for 'npm' | 'pip' | 'gem'. False means: never ask
    the registry about this name."""
    if registry not in ('npm', 'pip', 'gem'):
        return False
    if is_junk_name(name):
        return False
    if registry == 'npm':
        if name in NODE_CORE_MODULES:
            return False
        return bool(NPM_UNSCOPED.match(name) or NPM_SCOPED.match(name))
    if registry == 'pip':
        return bool(PYPI.match(name))
    return bool(GEM.match(name))


def valid_scope_name(scope: str) -> bool:
    """npm scope = the account name that must be claimable. Grammar plus
    stopwords; placeholder prefixes are legal in real npm usernames
    (my-org etc), so they are not applied here."""
    return bool(NPM_SCOPE.match(scope)) and scope.lower() not in STOPWORDS
