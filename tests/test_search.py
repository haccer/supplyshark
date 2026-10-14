from conftest import REPO
"""rg-stream extraction: MCP configs, shell pipes, reference matching."""
import json

from shark import search
from shark.clean import search as extract


def _read_stream(path):
    return search.read_matches(str(path))


def test_mcp_config_files_extracts_runner_packages(work_tree):
    repo_dir, output_root = work_tree
    search.mcp_config_files(str(repo_dir), "testuser")

    npm_stream = _read_stream(output_root / "testuser" / "npm_search.json")
    pip_stream = _read_stream(output_root / "testuser" / "pip_search.json")
    url_stream = _read_stream(output_root / "testuser" / "mcp_url_search.json")

    npm_matches = [item["match"] for item in npm_stream]
    pip_matches = [item["match"] for item in pip_stream]
    assert "npx supplysharkmcp-npm" in npm_matches
    assert "uvx supplysharkmcp-py" in pip_matches
    # node-based local server is not a registry reference
    assert not any("server.js" in m for m in npm_matches + pip_matches)

    entry = next(item for item in npm_stream if item["match"] == "npx supplysharkmcp-npm")
    assert entry["file"] == f"testuser/{REPO}/.cursor/mcp.json"

    # remote server URLs are collected for takeover/insecurity checks
    url_matches = {item["match"] for item in url_stream}
    assert url_matches == {"https://dead.invalid/mcp", "http://insecure.example/mcp"}

    # downstream extraction picks the package out of the synthetic match
    assert extract(["npx supplysharkmcp-npm"]) == ["supplysharkmcp-npm"]
    assert extract(["uvx supplysharkmcp-py"]) == ["supplysharkmcp-py"]


def test_mcp_runner_shapes(work_tree):
    repo_dir, output_root = work_tree
    search.mcp_config_files(str(repo_dir), "testuser")

    npm_matches = [item["match"] for item in _read_stream(output_root / "testuser" / "npm_search.json")]
    pip_matches = [item["match"] for item in _read_stream(output_root / "testuser" / "pip_search.json")]

    # python -m module (non-stdlib) resolves from PyPI; stdlib venv is skipped
    assert "pip install supplysharkpymod" in pip_matches
    assert not any("venv" in m for m in pip_matches)

    # uv run --with dep / uv tool run pull from PyPI like uvx
    assert "uvx uvwithfake-pkg" in pip_matches
    assert not any("localcmd" in m for m in pip_matches)

    # npx --package pkg cmd: the package is the flag value, not the bin name
    assert "npx npxflagfake-pkg" in npm_matches
    assert not any("binname" in m for m in npm_matches)

    # Windows cmd /c wrapper
    assert "npx cmdwrappedfake-pkg" in npm_matches

    # claude_desktop_config.json has no 'mcp' in its filename but must be found
    claude_entry = next(m for m in npm_matches if "claudefake-npm-pkg" in m)
    assert claude_entry == "npx claudefake-npm-pkg"


async def test_mcp_url_findings_classify(work_tree, monkeypatch):
    repo_dir, output_root = work_tree
    search.mcp_config_files(str(repo_dir), "testuser")

    async def fake_resolve(host):
        return False  # pretend nothing resolves

    async def fake_registered(apex):
        return False

    monkeypatch.setattr(search, "_resolve", fake_resolve)
    monkeypatch.setattr(search.registry, "domain_registered", fake_registered)
    findings = await search.mcp_url_findings(str(output_root / "testuser"))

    by_url = {item[0]["url"]: item[0]["reason"] for item in findings}
    # takeover-only: both endpoints sit on dead unregistered domains
    assert by_url == {"https://dead.invalid/mcp": "unregistered-domain",
                      "http://insecure.example/mcp": "unregistered-domain"}
    # refs are attached for permalinks
    dead = next(item for item in findings if item[0]["url"] == "https://dead.invalid/mcp")
    assert dead[1][0]["file"] == f"testuser/{REPO}/.cursor/mcp.json"


async def test_mcp_url_findings_skip_live_domains(work_tree, monkeypatch):
    repo_dir, output_root = work_tree
    search.mcp_config_files(str(repo_dir), "testuser")

    async def fake_resolve(host):
        return True  # everything resolves -> no takeovers, http or not

    monkeypatch.setattr(search, "_resolve", fake_resolve)
    findings = await search.mcp_url_findings(str(output_root / "testuser"))
    assert findings == []


async def test_reference_matching_is_boundary_aware(work_tree):
    repo_dir, output_root = work_tree
    stream = output_root / "testuser" / "boundary_search.json"
    with open(stream, "w") as f:
        for line in ["npm install foo", "pip install foo-bar", "yarn add foo==1.0.2"]:
            f.write(json.dumps({"file": f"testuser/{REPO}/x.md", "line_number": "1", "match": line}) + "\n")

    matches = await search.package_search_json_results(str(stream), "foo")
    # "foo-bar" and "foo==..." must not be attributed to "foo" via substring;
    # "foo==1.0.2" has a version specifier boundary so it *is* a reference
    matched_lines = [item[0]["match"] for item in matches]
    assert "npm install foo" in matched_lines
    assert "pip install foo-bar" not in matched_lines
    assert "yarn add foo==1.0.2" in matched_lines


def test_read_matches_missing_file(work_tree):
    _, output_root = work_tree
    assert search.read_matches(str(output_root / "testuser" / "nope.json")) == []


def test_find_urls_extracts_clean_hosts(work_tree):
    repo_dir, output_root = work_tree
    (repo_dir / "links.md").write_text(
        "registry=https://user:pass@nexus.corp.example.io:8081/pkg\n"
        "see http://localhost:8080/debug\n"
        "docs at https://github.com/foo/bar)\n"
        "badge https://img.shields.io/badge/x-y-blue.svg\n"
        "internal https://dead.invalid/x and http://10.0.0.5:9000\n"
    )
    search.find_urls(str(repo_dir), "testuser")

    hosts = {item["match"] for item in _read_stream(output_root / "testuser" / "urls_search.json")}
    # userinfo and port stripped, trailing paren cleaned
    assert "nexus.corp.example.io" in hosts
    assert "github.com" in hosts
    assert "img.shields.io" in hosts
    # localhost, RFC2606 TLDs, and IP literals never reach the stream
    assert not any(h in ("localhost", "dead.invalid", "10.0.0.5") for h in hosts)


def test_placeholder_hosts_are_dropped(work_tree):
    repo_dir, output_root = work_tree
    (repo_dir / "ph.md").write_text(
        "https://your.rpc.url\n"
        "https://your-webhook-endpoint.com/hook\n"
        "https://test.rpc\n"
        "https://shop.example.com/x\n"
        "https://test.com/a\n"
        "https://my.specific-domain.com/b\n"
        # real-looking internals survive
        "https://test-api.intuition.systems/v1\n"
        "https://my.corp.internal-reg.io/pkg\n"
    )
    search.find_urls(str(repo_dir), "testuser")
    hosts = {item["match"] for item in _read_stream(output_root / "testuser" / "urls_search.json")}
    assert hosts == {"test-api.intuition.systems", "my.corp.internal-reg.io",
                     # hosts from the fixture tree's own files
                     "github.com", "raw.githubusercontent.com",
                     "npm-registry.deadname-bbp-test.io"}


async def test_url_findings_reports_only_dead_hosts(work_tree, monkeypatch):
    repo_dir, output_root = work_tree
    copy_dir = output_root / "testuser"
    stream = copy_dir / "urls_search.json"
    with open(stream, "w") as f:
        for host, fname in [("dead.one.example.io", "a.md"), ("live.one.example.io", "b.md"),
                            ("mcp-covered.example.io", "c.md"), ("dead.one.example.io", "d.md")]:
            f.write(json.dumps({"file": f"testuser/{REPO}/{fname}", "line_number": "1", "match": host}) + "\n")
    with open(copy_dir / "mcp_url_search.json", "w") as f:
        f.write(json.dumps({"file": f"testuser/{REPO}/.cursor/mcp.json", "line_number": "2",
                            "match": "https://mcp-covered.example.io/mcp"}) + "\n")

    # apexes: example.io and root-dead.io's parent resolution semantics
    live = {"live.one.example.io", "mcp-covered.example.io", "example.io",
            "root-alive.io"} | set(search.CANARY_HOSTS)

    async def fake_resolve(host):
        return host in live

    monkeypatch.setattr(search, "_resolve", fake_resolve)

    rdap = {"root-dead.io": False, "regd-dead.io": True}

    async def fake_registered(apex):
        return rdap.get(apex)

    monkeypatch.setattr(search.registry, "domain_registered", fake_registered)

    with open(stream, "a") as f:
        f.write(json.dumps({"file": f"testuser/{REPO}/e.md", "line_number": "1",
                            "match": "sub.root-dead.io"}) + "\n")
        f.write(json.dumps({"file": f"testuser/{REPO}/f.md", "line_number": "1",
                            "match": "www.root-alive.io"}) + "\n")
        f.write(json.dumps({"file": f"testuser/{REPO}/g.md", "line_number": "1",
                            "match": "host.regd-dead.io"}) + "\n")

    findings = await search.url_findings(str(copy_dir))
    by_host = {item[0]["host"]: item for item in findings}
    # only claimable domains survive: apex-dead AND RDAP-unregistered.
    # dead.one.example.io has a live apex (internal-leak class, dropped);
    # regd-dead.io is registered (dropped); live/mcp-covered never counted;
    # www.* under a live apex is a stale doc link (dropped)
    assert set(by_host) == {"sub.root-dead.io"}
    assert by_host["sub.root-dead.io"][0]["reason"] == "unregistered-domain"


async def test_url_findings_skipped_when_resolver_broken(work_tree, monkeypatch, capsys):
    repo_dir, output_root = work_tree
    copy_dir = output_root / "testuser"
    with open(copy_dir / "urls_search.json", "w") as f:
        f.write(json.dumps({"file": f"testuser/{REPO}/a.md", "line_number": "1",
                            "match": "github.com"}) + "\n")

    async def dead_resolver(host):
        return False  # canaries fail -> resolver considered broken

    monkeypatch.setattr(search, "_resolve", dead_resolver)
    assert await search.url_findings(str(copy_dir)) == []
    assert "skipping dead-domain" in capsys.readouterr().out


def test_invented_tlds_are_dropped(work_tree):
    repo_dir, output_root = work_tree
    (repo_dir / "junk.md").write_text(
        "https://foo.chain/x https://a.b/y https://target.whatever/z\n"
        "https://explorer.private/w https://custom.chain/v\n"
        # real TLDs survive
        "https://nougat.world/a https://fulcrum.trade/b\n"
    )
    search.find_urls(str(repo_dir), "testuser")
    hosts = {item["match"] for item in _read_stream(output_root / "testuser" / "urls_search.json")}
    assert "nougat.world" in hosts and "fulcrum.trade" in hosts
    assert not any(h in ("foo.chain", "a.b", "target.whatever", "explorer.private", "custom.chain")
                   for h in hosts)


def test_doc_placeholder_vocabulary_dropped(work_tree):
    repo_dir, output_root = work_tree
    (repo_dir / "ph2.md").write_text(
        "https://foo.bar/x https://example-scam.com/y https://ekzample.com/z\n"
        "https://api.example-relayer.net/w https://api.example-relayer.com/v\n"
    )
    search.find_urls(str(repo_dir), "testuser")
    hosts = {item["match"] for item in _read_stream(output_root / "testuser" / "urls_search.json")}
    assert hosts == {"github.com", "raw.githubusercontent.com",
                     "npm-registry.deadname-bbp-test.io"}  # fixture tree's own hosts
