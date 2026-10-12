"""File classification into attack surfaces."""
from shark.surfaces import classify, classify_finding_file, package_surface


def test_agent_instruction_files():
    assert classify("CLAUDE.md") == "agent"
    assert classify("AGENTS.md") == "agent"
    assert classify("docs/CLAUDE.md") == "agent"
    assert classify("GEMINI.md") == "agent"
    assert classify(".cursorrules") == "agent"
    assert classify(".github/copilot-instructions.md") == "agent"
    assert classify(".cursor/rules/frontend.md") == "agent"
    assert classify(".clinerules/python.md") == "agent"
    assert classify(".windsurfrules") == "agent"


def test_ci_workflows():
    assert classify(".github/workflows/deploy.yml") == "ci"
    assert classify(".github/workflows/test.yaml") == "ci"
    assert classify(".github/workflows/deploy.yml.j2") is None


def test_package_json_hooks():
    assert classify("package.json") == "hook"
    assert classify("web/package.json") == "hook"


def test_plain_files_are_none():
    assert classify("README.md") is None
    assert classify("docs/guide.md") is None
    assert classify("requirements.txt") is None
    assert classify(".github/ISSUE_TEMPLATE.md") is None


def test_finding_file_values_strip_user_repo():
    assert classify_finding_file("testuser/tests/CLAUDE.md") == "agent"
    assert classify_finding_file("testuser/tests/.github/workflows/ci.yml") == "ci"
    assert classify_finding_file("testuser/tests/README.md") is None


def test_package_surface_priority():
    assert package_surface(["u/r/CLAUDE.md", "u/r/requirements.txt"]) == "agent"
    assert package_surface(["u/r/.github/workflows/ci.yml"]) == "ci"
    # hooks don't tag package findings
    assert package_surface(["u/r/package.json"]) is None
    assert package_surface(["u/r/README.md"]) is None
