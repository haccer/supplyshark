"""npm candidate extraction and availability checks."""
from urllib.parse import unquote

from shark import npm, registry, search


async def test_find_package_json_excludes_shorthand_and_git_refs(work_tree):
    repo_dir, output_root = work_tree
    copy_dir = output_root / "testuser"
    search.copy_files(str(repo_dir), "testuser", "tests", "package.json")

    packages = await npm.find_package_json(str(copy_dir))
    assert sorted(packages) == [
        "@asldkjsupplyshark4/test",
        "@json-rpc-tools/utils",
        "angular",
        "angular-mocks",
        "babel-core",
    ]


async def test_package_missing(fake_registry):
    assert await npm.package_missing("supplysharktest1") is True
    assert await npm.package_missing("@asldkjsupplyshark/test9") is True
    assert await npm.package_missing("angular") is False
    assert await npm.package_missing("@json-rpc-tools/utils") is False


async def test_package_missing_checks_case_variants(monkeypatch):
    """An uppercase spelling whose lowercase form is registered must not be
    reported available: the check falls back to the lowercased name."""
    async def status(url, browser=False):
        name = unquote(url.removeprefix("https://registry.npmjs.org/"))
        return 404 if name == "Case-Pkg" else 200

    monkeypatch.setattr(registry, "status", status)
    assert await npm.package_missing("Case-Pkg") is False


async def test_scope_status_verdicts(monkeypatch):
    from shark import npm

    codes = {"https://www.npmjs.com/~intuition": 200,
             "https://www.npmjs.com/~free-scope": 404,
             "https://www.npmjs.com/~blocked": 403}

    async def fake_status(url, browser=False):
        return codes.get(url)

    async def fake_populated(name):
        return name == "populated-org"

    async def fake_missing(package):
        return not package.endswith("-exists")

    monkeypatch.setattr(npm.registry, "status", fake_status)
    monkeypatch.setattr(npm, "scope_populated", fake_populated)
    monkeypatch.setattr(npm, "package_missing", fake_missing)
    npm._scope_status_cache.clear()

    # any existing package under the scope proves taken, no www needed
    assert await npm.scope_status("probed", ["@probed/pkg-exists"]) == "taken"
    npm._scope_status_cache.clear()
    assert await npm.scope_status("intuition") == "taken"
    assert await npm.scope_status("free-scope") == "available"
    # blocked page + populated via search => taken
    npm._scope_status_cache.clear()
    assert await npm.scope_status("populated-org") == "taken"
    # blocked page + unpopulated => unknown
    npm._scope_status_cache.clear()
    assert await npm.scope_status("blocked") == "unknown"


async def test_scope_check_taken_drops_everything(work_tree, monkeypatch):
    repo_dir, output_root = work_tree
    search.get_packages(str(repo_dir), "testuser", "tests")

    async def taken(name, probe_packages=()):
        return "taken"

    monkeypatch.setattr(npm, "scope_status", taken)
    npm._scope_status_cache.clear()

    results = await npm.scope_check(str(output_root / "testuser"),
                                    "@asldkjsupplyshark",
                                    ["@asldkjsupplyshark/test9", "@asldkjsupplyshark/test10"])
    assert results == []


async def test_scope_check_available_covers_all_packages(work_tree, monkeypatch):
    repo_dir, output_root = work_tree
    search.get_packages(str(repo_dir), "testuser", "tests")

    async def available(name, probe_packages=()):
        return "available"

    monkeypatch.setattr(npm, "scope_status", available)
    npm._scope_status_cache.clear()

    results = await npm.scope_check(str(output_root / "testuser"),
                                    "@asldkjsupplyshark",
                                    ["@asldkjsupplyshark/test9", "@asldkjsupplyshark/test10"])
    assert results[0]["scope"] == "@asldkjsupplyshark"
    assert results[0]["packages"] == ["@asldkjsupplyshark/test10", "@asldkjsupplyshark/test9"]
    assert "unverified" not in results[0]
    # refs cite where the scope's packages are used
    files = {ref[0]["file"] for ref in results[1:]}
    assert "testuser/tests/aREADME.md" in files


async def test_scope_check_unknown_marks_unverified(work_tree, monkeypatch):
    repo_dir, output_root = work_tree
    search.get_packages(str(repo_dir), "testuser", "tests")

    async def unknown(name, probe_packages=()):
        return "unknown"

    monkeypatch.setattr(npm, "scope_status", unknown)
    npm._scope_status_cache.clear()

    results = await npm.scope_check(str(output_root / "testuser"),
                                    "@asldkjsupplyshark", ["@asldkjsupplyshark/test9"])
    assert results[0]["unverified"] is True

