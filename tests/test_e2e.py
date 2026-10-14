from conftest import REPO
"""End-to-end pipeline against the in-repo fixture (tests/conftest.py
builds the whole tree locally; no external repos are involved).

Runs the real extraction (ripgrep over the tree), the real reference
resolution and result formatting, with only the registry HTTP layer faked.
"""
import asyncio
import json

import shark
import supplyshark as ss
from shark import search

EXPECTED_NPM = {
    "agentfake-dep-pkg",
    "supplysharktest1", "supplysharktest2", "supplysharktest3",
    "supplysharktest4", "supplysharktest5", "supplysharktest6",
    "supplysharktest7", "supplysharktest8",
    # MCP runner shapes + agent-instruction surface (scoped names short-
    # circuit into scope-level findings below, not per-package findings)
    "npxflagfake-pkg", "claudefake-npm-pkg", "cmdwrappedfake-pkg",
    "agentfake-npm-pkg",
}

EXPECTED_SCOPES = {"@asldkjsupplyshark", "@asldkjsupplyshark4"}

EXPECTED_PIP = {f"supplysharktest{n}" for n in range(1, 13)} | {
    # agent-instruction, CI-workflow and MCP surfaces
    "agentfake-pkg", "cifake-pkg", "supplysharkpymod", "uvwithfake-pkg",
}

EXPECTED_GEM = {
    "supplysharktest1", "supplysharktest2", "supplysharktest3",
    "supplysharktest4", "freegemsupplyshark", "freegemsupplyshark2",
}

# names that must NEVER be reported (false-positive controls)
REAL_NAMES = {
    "requests", "angular", "angular-mocks", "babel-core",
    "@json-rpc-tools/utils", "railsmdb", "bundler",
    # git/file/github-shorthand deps are not registry-resolvable
    "supplyshark2", "supplyshark3", "supplyshark4", "supplyshark5",
    "@asldkjsupplyshark/ical.js", "hsl_rgb_converter",
    "jquery-timepicker", "jstzdetect", "notfreegem",
    # node_modules is out of scope
    "@supplysharkxoxo/angular",
}


async def run_pipeline(repo_dir, output_root):
    copy_dir = str(output_root / "testuser")
    search.get_packages(str(repo_dir), "testuser", REPO)

    sem = asyncio.Semaphore(10)
    super_sem = asyncio.Semaphore(50)
    npm_res, gem_res, pip_res, mcp_urls, urls = await asyncio.gather(
        ss.npm(copy_dir, sem, super_sem),
        ss.gem(copy_dir, super_sem),
        ss.pip(copy_dir, sem, super_sem),
        search.mcp_url_findings(copy_dir),
        search.url_findings(copy_dir),
    )
    return {
        "npm_results": npm_res["npm_results"],
        "gem_results": gem_res["gem_results"],
        "pip_results": pip_res["pip_results"],
        "mcp_url_results": mcp_urls,
        "url_results": urls,
    }


async def test_end_to_end_findings(work_tree, fake_registry, fake_dns, tmp_path):
    repo_dir, output_root = work_tree
    data = await run_pipeline(repo_dir, output_root)

    npm_found = {r[0]["package"] for r in data["npm_results"]["package_results"]}
    pip_found = {r[0]["package"] for r in data["pip_results"]["package_results"]}
    gem_found = {r[0]["package"] for r in data["gem_results"]["package_results"]}

    assert npm_found == EXPECTED_NPM, f"npm mismatch: extra={npm_found - EXPECTED_NPM} missing={EXPECTED_NPM - npm_found}"
    assert pip_found == EXPECTED_PIP, f"pip mismatch: extra={pip_found - EXPECTED_PIP} missing={EXPECTED_PIP - pip_found}"
    assert gem_found == EXPECTED_GEM, f"gem mismatch: extra={gem_found - EXPECTED_GEM} missing={EXPECTED_GEM - gem_found}"

    leaked = (npm_found | pip_found | gem_found) & REAL_NAMES
    assert not leaked, f"false positives on real/excluded names: {leaked}"

    # scoped names collapse into one verdict per scope (fake says available)
    scopes = {r[0]["scope"] for r in data["npm_results"]["scope_results"]}
    assert scopes == EXPECTED_SCOPES
    asldkj = next(r for r in data["npm_results"]["scope_results"]
                  if r[0]["scope"] == "@asldkjsupplyshark")
    assert len(asldkj[0]["packages"]) == 8
    assert "unverified" not in asldkj[0]

    # remote MCP endpoints: takeover-only — the plaintext-http endpoint on
    # a live domain is not reported, the claimable-domain one is
    urls = {item[0]["url"] for item in data["mcp_url_results"]}
    assert urls == {"https://dead.invalid/mcp"}

    # stdlib modules and local commands from MCP configs are not packages
    all_found = npm_found | pip_found | gem_found
    assert not {"venv", "localcmd", "binname"} & all_found

    # only claimable domains are findings: the .npmrc host has a live apex
    # (internal leak) and is dropped, and the MCP dead domain is not
    # double-reported under [domain]
    assert data["url_results"] == []


async def test_results_file_format(work_tree, fake_registry, fake_dns, tmp_path):
    repo_dir, output_root = work_tree
    data = await run_pipeline(repo_dir, output_root)

    results_file = tmp_path / "results.txt"
    repos = [{"repo_name": REPO, "default_branch": "main"}]
    total = shark.results.process_results(json.dumps(data), repos, str(results_file))

    text = results_file.read_text()
    expected_total = (len(EXPECTED_NPM) + len(EXPECTED_PIP) + len(EXPECTED_GEM)
                      + 1 + len(EXPECTED_SCOPES))  # + mcp-url + scopes
    assert total == expected_total
    assert "[npm scope] @asldkjsupplyshark (packages:" in text
    for label in ("[npm]", "[pip]", "[gem]", "[mcp-url]",
                  "[pip:agent]", "[npm:agent:runner]", "[npm:dep]", "[pip:ci]"):
        assert label in text, f"missing label {label}"
    assert "[cmd]" not in text  # command-injection class removed entirely
    # permalinks carry the default branch, not None
    assert "blob/main/" in text
    assert "blob/None" not in text
    assert f"https://github.com/testuser/{REPO}/blob/main/aREADME.md" in text
