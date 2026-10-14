"""Exec-path tagging (:runner / :dep / :dev) — the severity dimension
that survives npm >=11's install-script gating.

runner: name is fetched-and-executed via npx/bunx -> version-independent
dep:   name is a runtime dependency -> the victim's code imports it ->
       module body executes at import time, version-independent
dev:   devDependency -> executes via tooling that loads declared
       plugins/modules by name (eslint, jest, webpack, vite, ...)
"""
import asyncio
import json

import pytest

import shark.npm as npm
from shark import registry
from conftest import make_fake_status


def _mkrepo(tmp_path, deps=None, devdeps=None, stream=None, repo="fixture-repo"):
    repo_dir = tmp_path / repo
    repo_dir.mkdir(parents=True, exist_ok=True)
    pkg = {"name": "app", "dependencies": deps or {}, "devDependencies": devdeps or {}}
    (repo_dir / "package.json").write_text(json.dumps(pkg))
    if stream:
        f = tmp_path / "npm_search.json"
        with open(f, "a") as fh:
            for line in stream:
                fh.write(json.dumps({"file": f"testuser/{repo}/docs.md",
                                     "line_number": "1", "match": line}) + "\n")
    return tmp_path


@pytest.mark.asyncio
async def test_runner_tag_for_npx_stream_refs(tmp_path, monkeypatch):
    _mkrepo(tmp_path, stream=["npx runnerfake-pkg --watch"])
    monkeypatch.setattr(registry, "status", make_fake_status({"runnerfake-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "runnerfake-pkg")
    assert result and result[0]["exec"] == "runner"


@pytest.mark.asyncio
async def test_dep_tag_for_runtime_dependency(tmp_path, monkeypatch):
    # manifest-only finding: package.json declares it under dependencies
    _mkrepo(tmp_path, deps={"depfake-pkg": "^1.0.0"})
    monkeypatch.setattr(registry, "status", make_fake_status({"depfake-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "depfake-pkg")
    assert result and result[0]["exec"] == "dep"


@pytest.mark.asyncio
async def test_dev_tag_for_dev_dependency(tmp_path, monkeypatch):
    _mkrepo(tmp_path, devdeps={"devfake-pkg": "^1.0.0"})
    monkeypatch.setattr(registry, "status", make_fake_status({"devfake-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "devfake-pkg")
    assert result and result[0]["exec"] == "dev"


@pytest.mark.asyncio
async def test_runner_beats_dep_when_both_present(tmp_path, monkeypatch):
    # the victim both depends on the name (repo-a) and npx-runs it in docs
    # where no local bin exists (repo-b): runner wins as the strongest path
    _mkrepo(tmp_path, deps={"bothfake-pkg": "^1.0.0"}, repo="repo-a")
    _mkrepo(tmp_path, stream=["npx bothfake-pkg"], repo="repo-b")
    monkeypatch.setattr(registry, "status", make_fake_status({"bothfake-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "bothfake-pkg")
    assert result and result[0]["exec"] == "runner"


@pytest.mark.asyncio
async def test_shadowed_npx_degrades_to_dep_tag(tmp_path, monkeypatch):
    """The shadow rule drops the npx ref when the same repo declares the
    dependency (local bin wins); the surviving manifest path tags :dep."""
    _mkrepo(tmp_path, deps={"bothfake-pkg": "^1.0.0"},
            stream=["npx bothfake-pkg"])
    monkeypatch.setattr(registry, "status", make_fake_status({"bothfake-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "bothfake-pkg")
    assert result and result[0]["exec"] == "dep"


@pytest.mark.asyncio
async def test_dep_beats_dev_when_both_present(tmp_path, monkeypatch):
    # declared as a runtime dep in one repo, dev dep in another: runtime wins
    _mkrepo(tmp_path, deps={"mixfake-pkg": "^1.0.0"}, repo="repo-a")
    _mkrepo(tmp_path, devdeps={"mixfake-pkg": "^1.0.0"}, repo="repo-b")
    monkeypatch.setattr(registry, "status", make_fake_status({"mixfake-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "mixfake-pkg")
    assert result and result[0]["exec"] == "dep"


@pytest.mark.asyncio
async def test_no_tag_for_docs_only_mentions(tmp_path, monkeypatch):
    # install-command stream ref only, no manifest, no runner: plain [npm]
    _mkrepo(tmp_path, stream=["npm install plaindocs-pkg"])
    monkeypatch.setattr(registry, "status", make_fake_status({"plaindocs-pkg"}))
    result = await npm.scan_packages(str(tmp_path), "plaindocs-pkg")
    assert result and "exec" not in result[0]
