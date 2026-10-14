"""--npm/--pip/--gem registry selection: flag parsing, partial-result
handling, and the scan-skip wiring end to end (hermetic)."""
import asyncio
import json
from argparse import Namespace
from pathlib import Path
from shutil import copytree

import pytest

import shark.github
import shark.results
import supplyshark
from conftest import REPO, USERNAME, build_test_repo


def _args(**kw):
    return Namespace(npm=kw.get("npm", False), pip=kw.get("pip", False),
                     gem=kw.get("gem", False))


def test_no_flags_means_all_registries():
    assert supplyshark.selected_registries(_args()) == ["npm", "pip", "gem"]


def test_single_registry_flags():
    assert supplyshark.selected_registries(_args(npm=True)) == ["npm"]
    assert supplyshark.selected_registries(_args(pip=True)) == ["pip"]
    assert supplyshark.selected_registries(_args(gem=True)) == ["gem"]


def test_multiple_flags_union():
    assert supplyshark.selected_registries(_args(npm=True, gem=True)) == ["npm", "gem"]


def test_process_results_tolerates_partial_data(tmp_path):
    """A gem-only run produces a result dict without npm/pip keys."""
    out = tmp_path / "results.txt"
    repos = [{"repo_name": REPO, "default_branch": "main"}]
    data = json.dumps({
        "gem_results": {"package_results": []},
        "mcp_url_results": [],
        "url_results": [],
    })
    assert shark.results.process_results(data, repos, str(out)) == 0
    assert not out.exists() or out.read_text() == ""


@pytest.mark.asyncio
async def test_start_cli_gem_only_skips_other_scans(tmp_path, monkeypatch,
                                                    work_tree, fake_registry,
                                                    fake_dns, capsys):
    """End to end: with registries=("gem",) the npm and pip scans never
    run (their output files are never even written) and the skip messages
    say so."""
    repo_dir, output_root = work_tree
    monkeypatch.setattr(supplyshark, "create_dir",
                        lambda account: (tmp_path / "tmp", output_root / USERNAME))

    def fake_gh_get_repos(user):
        return [REPO], [{"repo_name": REPO, "default_branch": "main"}]

    def fake_clone(user, repo):
        shark.search.get_packages(str(repo_dir), user, repo)

    monkeypatch.setattr(shark.github, "gh_get_repos", fake_gh_get_repos)
    monkeypatch.setattr(shark.github, "cli_gh_clone_repo", fake_clone)

    results, _ = await supplyshark.start_cli(USERNAME, None, False,
                                             registries=["gem"])
    captured = capsys.readouterr().out
    assert "Skipping npm scan" in captured
    assert "Skipping pip scan" in captured
    assert "Skipping gem scan" not in captured
    # npm/pip streams were never consumed into findings
    data = json.loads(results)
    assert data["npm_results"]["package_results"] == []
    assert data["npm_results"]["scope_results"] == []
    assert data["pip_results"]["package_results"] == []
    assert data["mcp_url_results"] == []
    assert data["url_results"] == []


@pytest.mark.asyncio
async def test_start_cli_all_registries_default(tmp_path, monkeypatch,
                                                work_tree, fake_registry,
                                                fake_dns, capsys):
    repo_dir, output_root = work_tree
    monkeypatch.setattr(supplyshark, "create_dir",
                        lambda account: (tmp_path / "tmp", output_root / USERNAME))

    def fake_gh_get_repos(user):
        return [REPO], [{"repo_name": REPO, "default_branch": "main"}]

    def fake_clone(user, repo):
        shark.search.get_packages(str(repo_dir), user, repo)

    monkeypatch.setattr(shark.github, "gh_get_repos", fake_gh_get_repos)
    monkeypatch.setattr(shark.github, "cli_gh_clone_repo", fake_clone)

    results, _ = await supplyshark.start_cli(USERNAME, None, False)
    captured = capsys.readouterr().out
    assert "Skipping" not in captured
    data = json.loads(results)
    # the full fixture run finds npm packages again
    assert data["npm_results"]["package_results"]
