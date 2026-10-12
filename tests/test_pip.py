"""PyPI candidate extraction and availability checks."""
import pytest

from shark import pip, registry
from shark.pip import find_pyproject_toml, normalize_pypi, parse_requirement


@pytest.mark.parametrize("line,expected", [
    ("requests", "requests"),
    ("zope_interface>=5.0", "zope_interface"),
    ("requests[security]>=2.0", "requests"),
    ("flask ; python_version<'4'", "flask"),
    ("pkg-with-dashes==1.0.0", "pkg-with-dashes"),
    ("  spaces-pkg  == 1.0", "spaces-pkg"),
    # skipped forms
    ("# comment", None),
    ("-r other-requirements.txt", None),
    ("-e .", None),
    ("--index-url https://example.com/simple", None),
    ("direct-ref @ https://github.com/x/y", None),
    ("", None),
])
def test_parse_requirement(line, expected):
    assert parse_requirement(line) == expected


async def test_find_requirements_txt(work_tree):
    repo_dir, _ = work_tree
    names = await pip.find_requirements_txt(repo_dir)
    assert sorted(names) == [
        "supplysharktest10", "supplysharktest11", "supplysharktest12", "supplysharktest9",
    ]


def test_find_pyproject_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("""
[project]
dependencies = ["toml>=0.10", "pep621-pkg>=1.0"]

[tool.poetry.dependencies]
python = "^3.10"
poetry-pkg = "^1.0"
gitdep = { git = "https://github.com/example/gitdep.git" }
pathdep = { path = "../local" }
""")
    assert sorted(find_pyproject_toml(tmp_path)) == ["pep621-pkg", "poetry-pkg", "toml"]


@pytest.mark.parametrize("name,normalized", [
    ("Django", "django"),
    ("zope_interface", "zope-interface"),
    ("Pillow._patch", "pillow-patch"),
])
def test_normalize_pypi(name, normalized):
    assert normalize_pypi(name) == normalized


async def test_package_missing(fake_registry):
    assert await pip.package_missing("supplysharktest9") is True
    assert await pip.package_missing("requests") is False


async def test_scan_packages_reports_refs(work_tree, fake_registry):
    repo_dir, output_root = work_tree
    copy_dir = output_root / "testuser"
    from shark import search
    search.get_packages(str(repo_dir), "testuser", "tests")

    results = await pip.scan_packages(str(copy_dir), "supplysharktest9")
    assert results, "planted fake must be reported"
    refs = [item for group in results[1:] for item in group]
    assert any(r["file"] == "testuser/tests/pip/requirements.txt" for r in refs)

    assert await pip.scan_packages(str(copy_dir), "requests") == []
