"""RubyGems availability checks."""
from shark import gem, search


async def test_gem_missing(fake_registry):
    assert await gem.gem_missing("freegemsupplyshark") is True
    assert await gem.gem_missing("supplysharktest3") is True
    assert await gem.gem_missing("railsmdb") is False
    assert await gem.gem_missing("bundler") is False


async def test_scan_gems_reports_gemfile_refs(work_tree, fake_registry):
    repo_dir, output_root = work_tree
    search.get_packages(str(repo_dir), "testuser", "tests")

    results = await gem.scan_gems(str(output_root / "testuser"), "freegemsupplyshark")
    assert results and results[0] == {"package": "freegemsupplyshark"}
    files = {item[0]["file"] for item in results[1:]}
    assert files == {"testuser/tests/Gemfile"}
