#!/usr/bin/env python3
"""Build lists/bbp.txt: merge the legacy wordlist with GitHub org/user
handles extracted from Immunefi's unofficial programs list.

Sources per project: the top-level githubUrl field, asset URLs, links, and
any github.com/<handle> reference in text fields. Reserved GitHub path
segments (github.com/features etc.) are filtered out.

Usage:
    python scripts/build_bbp.py                  # download and merge
    python scripts/build_bbp.py --file projects.json
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

IMMUNEFI_URL = ("https://raw.githubusercontent.com/infosec-us-team/"
                "Immunefi-Bug-Bounty-Programs-Unofficial/refs/heads/main/projects.json")

LISTS_DIR = Path(__file__).resolve().parent.parent / "lists"
BBP_FILE = LISTS_DIR / "bbp.txt"

GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9-]{2,39})(?:/[A-Za-z0-9._-]+)*", re.IGNORECASE)

# github.com/<reserved> pages that are not accounts
RESERVED = {
    "sponsors", "site", "about", "topics", "features", "security",
    "settings", "login", "logout", "signup", "marketplace", "apps",
    "notifications", "explore", "new", "pricing", "enterprise", "orgs",
    "organizations", "users", "gist", "gists", "raw", "api", "www",
    "blog", "docs", "support", "legal", "privacy", "terms", "codespaces",
    "copilot", "collections", "events", "readme", "profile",
    "repositories", "stars", "following", "followers", "search", "pulls",
    "issues", "notifications", "watching", "custom-infra",
}


def iter_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)
    elif isinstance(node, str):
        yield node


def extract_handles(projects) -> set:
    handles = set()
    for project in projects:
        github_url = project.get("githubUrl")
        if isinstance(github_url, str):
            match = re.match(r"https?://github\.com/([A-Za-z0-9-]{2,39})/?", github_url, re.IGNORECASE)
            if match:
                handles.add(match.group(1).lower())
        for text in iter_strings(project):
            for match in GITHUB_RE.finditer(text):
                handles.add(match.group(1).lower())
    return {h for h in handles if h not in RESERVED}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="path to a downloaded projects.json")
    args = parser.parse_args()

    if args.file:
        projects = json.loads(Path(args.file).read_text())
    else:
        print(f"[*] downloading {IMMUNEFI_URL}")
        with urllib.request.urlopen(IMMUNEFI_URL) as resp:
            projects = json.loads(resp.read())

    immunefi_handles = extract_handles(projects)

    LISTS_DIR.mkdir(exist_ok=True)
    legacy = set()
    if BBP_FILE.exists():
        legacy = {line.strip().lower() for line in BBP_FILE.read_text().splitlines()
                  if line.strip() and not line.startswith("#")}

    merged = sorted(legacy | immunefi_handles)
    BBP_FILE.write_text("\n".join(merged) + "\n")

    print(f"[+] legacy entries:  {len(legacy)}")
    print(f"[+] immunefi orgs:   {len(immunefi_handles)} ({len(immunefi_handles - legacy)} new)")
    print(f"[+] wrote {len(merged)} accounts -> {BBP_FILE}")


if __name__ == "__main__":
    sys.exit(main())
