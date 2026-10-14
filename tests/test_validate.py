"""shark/validate rules: registry grammars, junk names, template vars.

The shape classes below mirror a hand-triaged corpus of ~1000 findings from
a real sweep (0 valid names rejected, ~43% of false positives caught at the
name level). The LITERAL names from that corpus are deliberately NOT in
this file — they are live research targets — so every case here is a
synthetic name with the same shape. If a rule change makes one of these
fail, you are changing corpus-verified behavior on purpose; say so in the
commit message.
"""
import pytest

from shark import validate


# ---------------------------------------------------------------- npm grammar

@pytest.mark.parametrize("name", [
    "abc", "a", "ab-cd", "a.b_c-d", "0abc", "x_",
    "@scope/pkg", "@my-org-2/tool.name", "@s/p",
])
def test_npm_valid(name):
    assert validate.valid_package("npm", name)


@pytest.mark.parametrize("name", [
    "NotLower", "@Scope/pkg", "@scope/Pkg", " leading", "trailing ",
    ".leading-dot", "_leading-underscore", "trailing-dot.", "trailing-dash-",
    "with space", "with/slash", "semi;colon", "brack{et", "pipe|char",
    "js" + "on" + "{" + "x",  # brace in middle
    "", "3.13", "1.2.3", "v2.0", "10.1.0",
])
def test_npm_invalid(name):
    assert not validate.valid_package("npm", name)


@pytest.mark.parametrize("name", ["fs", "dns", "child_process", "crypto", "zlib"])
def test_node_core_modules_blocked_for_npm_only(name):
    assert not validate.valid_package("npm", name)
    # the same spellings are legal on other registries
    assert validate.valid_package("pip", name)
    assert validate.valid_package("gem", name)


def test_url_words_are_junk_everywhere():
    # 'http'/'https'/'www' appeared only as FP artifacts in the corpus
    for name in ("http", "https", "www"):
        for registry in ("npm", "pip", "gem"):
            assert not validate.valid_package(registry, name)


# ---------------------------------------------------------------- pip grammar

@pytest.mark.parametrize("name", [
    "abc", "Corp_Lib", "corp-internal-lib", "a.b", "x9", "Ab_9",
])
def test_pypi_valid(name):
    assert validate.valid_package("pip", name)


@pytest.mark.parametrize("name", [
    "_under", "-dash", "dot.", "sp ace", "", "3.13", "1.2.3",
])
def test_pypi_invalid(name):
    assert not validate.valid_package("pip", name)


# ---------------------------------------------------------------- gem grammar

@pytest.mark.parametrize("name", ["abc", "Mixed-Case_1.x", "g0"])
def test_gem_valid(name):
    assert validate.valid_package("gem", name)


@pytest.mark.parametrize("name", ["_x", "x.", "a b", "", "2.0"])
def test_gem_invalid(name):
    assert not validate.valid_package("gem", name)


# ---------------------------------------------------------------- scope names

@pytest.mark.parametrize("scope", ["acme", "my-org-2", "x9"])
def test_scope_valid(scope):
    assert validate.valid_scope_name(scope)


@pytest.mark.parametrize("scope", ["Acme", "under_score", "with.dot", "", "-x", "x-"])
def test_scope_invalid(scope):
    assert not validate.valid_scope_name(scope)


# ---------------------------------------------------------------- junk rules

@pytest.mark.parametrize("name", [
    # prose/echo/comment extractions — each was a real FP class
    "git", "error", "requirements", "from", "docs", "client", "cache",
    "python", "finished", "capabilities", "does-not-exist",
    # placeholder/tutorial vocabulary
    "my-tool", "your-app", "example-foo", "sample-lib", "demo-thing",
    "test-helper", "dummy-pkg", "placeholder-x", "some-lib", "our-tool",
    # metasyntactic fixture names
    "foo", "qux", "garply", "waldo",
    # version strings and numerics
    "3.13", "1.0.0", "v1.2", "42",
])
def test_junk_names(name):
    for registry in ("npm", "pip", "gem"):
        assert not validate.valid_package(registry, name), (registry, name)


@pytest.mark.parametrize("name", [
    # near-miss shapes that MUST survive: each mirrors a real valid finding
    "install",        # a historical (currently unregistered) real package
    "pkg-release",    # corp tooling; 'pkg-' is not placeholder vocabulary
    "tac",            # 3-letter CLI abbreviation
    "w3f",            # alphanumeric short name
    "corp_lib",       # underscored internal name
    "corp.internal.tool",  # dotted internal name
    "lib-dotted.name",
])
def test_near_misses_survive(name):
    assert not validate.is_junk_name(name)


def test_length_bounds():
    assert not validate.valid_package("npm", "x" * 215)
    assert validate.valid_package("npm", "x" * 214)


# ------------------------------------------------------------- template vars

def test_strip_template_vars():
    assert validate.strip_template_vars("hiredis${{inputs.hiredis-version}}") == "hiredis"
    # unclosed interpolation (a real artifact shape) still strips
    assert validate.strip_template_vars("hiredis${{inputs.v") == "hiredis"
    assert validate.strip_template_vars("plain line") == "plain line"
    assert validate.strip_template_vars("${var}-prefix") == "-prefix"


# ------------------------------------------------- corpus-derived shape sweep

# one synthetic representative per shape class of the 211 VALID findings
VALID_SHAPES = {
    "npm": [
        "shortcli",                       # 3-8 char CLI (largest class)
        "corp-internal-lib",              # hyphenated corporate internal
        "corp_internal",                  # underscored corporate internal
        "corp.dotted.tool",               # dotted tooling name
        "part-ners-layerzone",            # partner/prefixed compound
        "@claimable-scope/sdk",           # scoped, unclaimed scope
        "@corp-org/deep.pkg-name",        # scoped with dots in package
        "publisher-pending-cli",          # own-name pre-publish squat
        "0xicorn-sdk",                    # hex-prefix web3 style
    ],
    "pip": [
        "shortcli",
        "corp-internal-lib",
        "corp_internal",
        "corp.dotted",
        "team_task_api",                  # underscored internal API lib
        "install",                        # historical real name, unpinned
        "0xtool",
        "corp-logging",
    ],
    "gem": [
        "shortcli",
        "corp_internal_gem",
        "corp-dotted-gem",
    ],
}

# one synthetic representative per shape class of rejected FP names
JUNK_SHAPES = {
    "npm": ["", "3.13", "git", "my-tool", "foo", "fs", "NotReal", "a/b"],
    "pip": ["", "10.1.0", "error", "your-lib", "bar", "-bad", "x y"],
    "gem": ["", "2.0", "for", "example-gem", "qux"],
}


def test_valid_shape_sweep():
    for registry, names in VALID_SHAPES.items():
        for name in names:
            assert validate.valid_package(registry, name), (registry, name)


def test_junk_shape_sweep():
    for registry, names in JUNK_SHAPES.items():
        for name in names:
            assert not validate.valid_package(registry, name), (registry, name)
