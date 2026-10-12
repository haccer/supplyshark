"""Extraction of package names from install-command lines and gem lines."""
from shark.clean import search, gem_search, package


def test_prose_and_flags_are_dropped():
    lines = [
        "npm install the following packages",
        "pip install -r requirements.txt",
        "yarn install",
        "pip install -e .",
    ]
    assert search(lines) == []


def test_runner_commands_take_first_argument():
    lines = [
        "npx create-react-app my-app",
        "uvx ruff check .",
        "bunx prettier --write .",
        "pnpm dlx oxlint",
    ]
    assert search(lines) == ["create-react-app", "ruff", "prettier", "oxlint"]


def test_install_variants():
    lines = [
        "npm install lodash",
        "npm install -g serve",
        "npm install --save-dev jest",
        "yarn add -D left-pad",
        "poetry add requests",
        "uv add fastapi",
        "pipx install httpie",
        "uv tool install httpie",
        "pip install package-name>=1.0",
    ]
    assert search(lines) == [
        "lodash", "serve", "jest", "left-pad", "requests",
        "fastapi", "httpie", "httpie", "package-name",
    ]


def test_scoped_names_survive():
    assert search(["npm install @asldkjsupplyshark/test9"]) == ["@asldkjsupplyshark/test9"]


def test_file_tokens_and_paths_are_dropped():
    for bad in ["requirements.txt", "pyproject.toml", "config.yaml", "/usr/local/bin", "-r"]:
        assert package(bad) == ""


def test_gem_extraction():
    lines = [
        "gem 'rails', '~> 7.0'",
        "gem install bundler",
        "gem \"puma\"",
        "gem i rake",
        "gem 'notfreegem', git: github.com/supplyshark",
        "gem 'vendored', path: 'vendor/gem'",
    ]
    assert gem_search(lines) == ["rails", "bundler", "puma", "rake"]


def test_version_specifiers_are_stripped():
    lines = [
        "npm install @openzeppelin/contracts@v2.5",
        "npm install @0xintuition/protocol@alpha",
        "npm install left-pad@1.2.0",
        "npx @modelcontextprotocol/server-memory@latest",
    ]
    assert search(lines) == [
        "@openzeppelin/contracts", "@0xintuition/protocol", "left-pad",
        "@modelcontextprotocol/server-memory",
    ]
