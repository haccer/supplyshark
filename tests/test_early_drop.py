"""Early-drop guarantees: junk names must never reach the registry layer,
and the new false-positive suppressions must keep real findings alive.

Every name here is synthetic (see test_validate.py for the shape-class
rationale): no live research targets appear in this suite.
"""
import json

import pytest

import shark.npm as npm
import shark.pip as pip
import shark.gem as gem
from conftest import make_fake_status
from shark import registry


# ---------------------------------------------------------------- early drop

@pytest.mark.asyncio
async def test_npm_junk_never_hits_registry(monkeypatch):
    calls = []
    monkeypatch.setattr(registry, "status", make_fake_status(set(), calls))
    for junk in ("", "git", "3.13", "my-tool", "fs", "NotReal"):
        assert await npm.scan_packages("/nonexistent", junk) == []
    assert calls == []


@pytest.mark.asyncio
async def test_pip_junk_never_hits_registry(monkeypatch):
    calls = []
    monkeypatch.setattr(registry, "status", make_fake_status(set(), calls))
    for junk in ("", "error", "10.1.0", "your-lib", "_bad"):
        assert await pip.scan_packages("/nonexistent", junk) == []
    assert calls == []


@pytest.mark.asyncio
async def test_gem_empty_and_junk_never_hit_registry(monkeypatch):
    """The empty-gem bug class: '' once matched every line of every repo
    and produced findings citing hundreds of files."""
    calls = []
    monkeypatch.setattr(registry, "status", make_fake_status(set(), calls))
    for junk in ("", "for", "qux", "2.0"):
        assert await gem.scan_gems("/nonexistent", junk) == []
    assert calls == []


@pytest.mark.asyncio
async def test_scope_junk_never_hits_registry(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(registry, "status", make_fake_status(set(), calls))

    async def boom(name, probe_packages=()):
        raise AssertionError("scope_status must not be called for junk scopes")

    monkeypatch.setattr(npm, "scope_status", boom)
    assert await npm.scope_check(str(tmp_path), "@NotValid!", ["@notvalid!/x"]) == []
    assert await npm.scope_check(str(tmp_path), "@3.13", ["@3.13/x"]) == []
    assert calls == []


# ------------------------------------------------------------- npx bin shadow

def _stream(path, lines, repo="fixture-repo", fname="docs.md"):
    f = path / "npm_search.json"
    with open(f, "a") as fh:
        for line in lines:
            fh.write(json.dumps({"file": f"testuser/{repo}/{fname}",
                                 "line_number": "1", "match": line}) + "\n")


@pytest.mark.asyncio
async def test_npx_shadowed_by_declared_dependency_dropped(tmp_path, monkeypatch):
    """`npx shadowtool` in a repo whose package.json declares
    @vendor/shadowtool never consults the public registry for the bare
    name — the bin resolves locally."""
    (tmp_path / "fixture-repo").mkdir(parents=True)
    (tmp_path / "fixture-repo" / "package.json").write_text(json.dumps({
        "name": "app", "dependencies": {"@vendor/shadowtool": "^1.0.0"}}))
    _stream(tmp_path, ["npx shadowtool --watch"])
    monkeypatch.setattr(registry, "status", make_fake_status({"shadowtool"}))

    assert await npm.scan_packages(str(tmp_path), "shadowtool") == []


@pytest.mark.asyncio
async def test_npx_unshadowed_name_survives(tmp_path, monkeypatch):
    (tmp_path / "fixture-repo").mkdir(parents=True)
    (tmp_path / "fixture-repo" / "package.json").write_text(json.dumps({
        "name": "app", "dependencies": {"left-pad": "^1.0.0"}}))
    _stream(tmp_path, ["npx realcli --watch", "npm install realcli"])
    monkeypatch.setattr(registry, "status", make_fake_status({"realcli"}))

    result = await npm.scan_packages(str(tmp_path), "realcli")
    assert result and result[0]["package"] == "realcli"
    assert len(result) == 3  # header + both refs


@pytest.mark.asyncio
async def test_npm_install_refs_not_subject_to_shadow_rule(tmp_path, monkeypatch):
    """Only runner lines (npx/bunx) resolve local bins; plain dependency
    declarations always resolve from the registry."""
    (tmp_path / "fixture-repo").mkdir(parents=True)
    (tmp_path / "fixture-repo" / "package.json").write_text(json.dumps({
        "name": "app", "dependencies": {"@vendor/libthing": "^1.0.0"}}))
    _stream(tmp_path, ["npm install libthing"])
    monkeypatch.setattr(registry, "status", make_fake_status({"libthing"}))

    result = await npm.scan_packages(str(tmp_path), "libthing")
    assert result and result[0]["package"] == "libthing"


# ---------------------------------------------------------- .npmrc scope pins

@pytest.mark.asyncio
async def test_scope_pinned_to_private_registry_dropped(tmp_path, monkeypatch):
    """@scope:registry=<private> in a repo .npmrc: publishing to the public
    registry can never capture those installs."""
    repo = tmp_path / "fixture-repo"
    repo.mkdir(parents=True)
    (repo / ".npmrc").write_text(
        "@pinzone:registry=https://npm.pkg.github.com/\nalways-auth=true\n")
    _stream(tmp_path, ["npm install @pinzone/tool"])
    monkeypatch.setattr(registry, "status",
                        make_fake_status({"@pinzone/tool"}))

    assert await npm.scan_packages(str(tmp_path), "@pinzone/tool") == []


@pytest.mark.asyncio
async def test_default_registry_pin_does_not_drop(tmp_path, monkeypatch):
    """A repo-wide default registry (proxies with public fallback are
    common) is NOT treated as a pin — only explicit @scope pins are."""
    repo = tmp_path / "fixture-repo"
    repo.mkdir(parents=True)
    (repo / ".npmrc").write_text("registry=https://mirror.example.com/\n")
    _stream(tmp_path, ["npm install plainname"])
    monkeypatch.setattr(registry, "status", make_fake_status({"plainname"}))

    result = await npm.scan_packages(str(tmp_path), "plainname")
    assert result and result[0]["package"] == "plainname"
