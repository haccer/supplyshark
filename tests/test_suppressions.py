"""New pip-side false-positive suppressions: uv.sources redirects and
prose-masquerading-as-requirements files, plus the fixture-tree exclusion
that applies to every extraction stream.
"""
import json

import pytest

from shark import pip as shark_pip
from shark import search


# ---------------------------------------------------------- uv.sources redirect

PYPROJECT_UV = """
[project]
name = "app"
dependencies = [
    "redirected-git",
    "redirected-path",
    "redirected-url",
    "redirected-index",
    "normal-dep",
]

[tool.uv.sources]
redirected-git = { git = "https://example.com/repo.git" }
redirected-path = { path = "../local_pkg", editable = true }
redirected-url = { url = "https://example.com/wheel.whl" }
redirected-index = { index = "private" }
normal-dep = ">=1.0"
"""


def test_uv_sources_redirects_excluded(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_UV)
    names = shark_pip.find_pyproject_toml(tmp_path)
    # git/path/url redirects never resolve from PyPI for uv workflows
    assert "redirected-git" not in names
    assert "redirected-path" not in names
    assert "redirected-url" not in names
    # index mappings still fall back to PyPI, and plain deps are untouched
    assert "redirected-index" in names
    assert "normal-dep" in names


# ------------------------------------------------- requirements content sniff

def test_bare_name_requirements_file_survives():
    """Real requirements files with no version pins (a valid-finding shape
    observed in the corpus) must not be flagged as prose."""
    text = "pylint\nvoluptuous\nyamllint\ncorp_internal_tool\nhelpers\nmisc\n"
    assert shark_pip._looks_like_requirements(text)


def test_prose_requirements_file_skipped():
    text = "\n".join([
        "or something like that", "in the beginning we had", "and the tool helps",
        "the design was simple", "with a few moving parts", "that changed later",
        "for reasons described above", "and documented elsewhere",
    ]) + "\n"
    assert not shark_pip._looks_like_requirements(text)


def test_small_files_always_survive():
    assert shark_pip._looks_like_requirements("one\ntwo\nthree\n")
    assert shark_pip._looks_like_requirements("")


def test_find_requirements_skips_prose_file(tmp_path):
    (tmp_path / "front-end-requirements.txt").write_text(
        "or install the tool\nin the usual way\nand it helps a lot\n"
        "the rest is history\nwith some notes\nfor later reading\n")
    (tmp_path / "real-requirements.txt").write_text(
        "real-dep==1.0.0\nother-dep>=2.0\nthird\n")
    import asyncio
    names = asyncio.run(shark_pip.find_requirements_txt(tmp_path))
    assert "real-dep" in names
    assert "or" not in names


# ------------------------------------------------------ fixture-tree exclusion

@pytest.fixture
def tree_with_fixture_dirs(tmp_path, monkeypatch):
    """A clone tree where install commands exist at the repo root AND
    inside spec/test/fixtures/testdata trees. Only the root references
    should be captured by the extraction streams."""
    root = tmp_path / "clone"
    for sub in ("spec", "test", "tests", "fixtures", "testdata", "src"):
        (root / sub).mkdir(parents=True)
    (root / "README.md").write_text(
        "npm install rootpkg\npip install rootpy\ngem install rootgem\n")
    (root / "spec" / "helper.rb").write_text("gem 'specgem'\n")
    (root / "test" / "x.py").write_text("# pip install testpy\n")
    (root / "tests" / "y.md").write_text("npm install testspkg\n")
    (root / "fixtures" / "z.js").write_text("// npm install fixturepkg\n")
    (root / "testdata" / "w.md").write_text("pip install datapkg\n")
    out = tmp_path / "output"
    (out / "testuser").mkdir(parents=True)
    monkeypatch.setattr(search, "OUTPUT_ROOT", out)
    return root, out


def _read(out, name):
    import json as _json
    path = out / "testuser" / name
    if not path.exists():
        return []
    return [_json.loads(l)["file"] for l in path.read_text().splitlines() if l.strip()]


def test_npm_stream_excludes_fixture_trees(tree_with_fixture_dirs):
    root, out = tree_with_fixture_dirs
    search.npm_install_files(str(root), "testuser")
    files = _read(out, "npm_search.json")
    assert any("README.md" in f for f in files)
    assert not any("fixtures" in f or "tests/" in f for f in files)


def test_pip_stream_excludes_fixture_trees(tree_with_fixture_dirs):
    root, out = tree_with_fixture_dirs
    search.pip_install_files(str(root), "testuser")
    files = _read(out, "pip_search.json")
    assert any("README.md" in f for f in files)
    assert not any("testdata" in f or "/test/" in f for f in files)


def test_gem_stream_excludes_spec_trees(tree_with_fixture_dirs):
    root, out = tree_with_fixture_dirs
    search.gem_install_files(str(root), "testuser")
    files = _read(out, "gem_search.json")
    assert any("README.md" in f for f in files)
    assert not any("/spec/" in f for f in files)


# ------------------------------------------------------ clean-level additions

def test_runner_package_flag_forms():
    from shark import clean
    assert clean._runner_package("--package=@vendor/control binname") == "@vendor/control"
    assert clean._runner_package("-p @vendor/control binname") == "@vendor/control"
    assert clean._runner_package("--with depname cmd") == "depname"
    assert clean._runner_package("plaincli --watch") == "plaincli"
    assert clean._runner_package("-y plaincli") == "plaincli"


def test_search_extracts_explicit_package_not_positional():
    from shark import clean
    names = clean.search(["npx --package=@vendor/control control-bin"])
    assert names == ["@vendor/control"]


def test_gem_search_empty_quoted_form_yields_nothing():
    from shark import clean
    assert clean.gem_search(["gem '", 'gem "', "gem 'realgem'"]) == ["realgem"]


def test_search_strips_template_vars():
    from shark import clean
    names = clean.search(["npm install hiredis${{inputs.hiredis-version"])
    assert names == ["hiredis"]
