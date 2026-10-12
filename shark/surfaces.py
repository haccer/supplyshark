"""Classification of files by the attack surface they expose.

Findings mean different things depending on where the reference lives:
an install command in a README may be followed by a human, the same
command in an agent-instruction file is followed automatically by AI
coding agents, in a CI workflow it executes on push, and in a package
lifecycle script it executes on install.
"""
import re

# instruction files agents read automatically, by filename, anywhere in the tree
AGENT_FILENAMES = {
    "claude.md", "agents.md", "gemini.md", "cursorrules",
    "windsurfrules", "clinerules", "copilot-instructions.md",
}

# directories whose *.md contents are agent instructions (e.g. .cursor/rules/foo.md)
AGENT_DIRS = {".cursor/rules", ".clinerules", ".clinerules/rules"}

WORKFLOW_RE = re.compile(r"\.ya?ml$", re.IGNORECASE)


def classify(repo_path: str) -> str | None:
    """Surface tag for a repo-relative path: 'agent', 'ci', 'hook', or None."""
    parts = [p.lower() for p in repo_path.split("/") if p]
    if not parts:
        return None
    name = parts[-1]
    joined = "/".join(parts)

    if name in AGENT_FILENAMES or name.lstrip(".") in AGENT_FILENAMES:
        return "agent"
    if any(joined == d or joined.startswith(d + "/") for d in AGENT_DIRS):
        return "agent"
    if ".github" in parts[:-1] and "workflows" in parts[:-1] and WORKFLOW_RE.search(name):
        return "ci"
    if name == "package.json":
        return "hook"

    return None


def classify_finding_file(finding_file: str) -> str | None:
    """Classify a '<user>/<repo>/<path>' file value from a finding."""
    parts = finding_file.split("/")
    return classify("/".join(parts[2:]) if len(parts) > 2 else finding_file)


def package_surface(files) -> str | None:
    """Strongest surface tag across reference files for a package finding.
    Hooks don't apply to dependency declarations, so only agent > ci."""
    tags = {t for t in (classify_finding_file(f) for f in files) if t in ("agent", "ci")}
    return "agent" if "agent" in tags else ("ci" if "ci" in tags else None)
