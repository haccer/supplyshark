#!/usr/bin/env python3
"""Build lists/bbp.txt: GitHub accounts of every bug-bounty program on
HackerOne, Bugcrowd, YesWeHack, and Immunefi.

Sources:
  - arkadiyt/bounty-targets-data (daily scrape of H1/BC/YWH policies and
    in-scope assets)
  - infosec-us-team Immunefi unofficial programs list

GitHub handles are extracted from in-scope assets (github.com/<org> scope
entries — the strongest signal) and from policy text. One account per line,
lowercased, deduped, merged with the existing list.

lists/exclude.txt (optional): accounts to always drop, one per line —
manual removals survive regeneration.

Usage:
    python scripts/build_bbp.py                  # download and merge
    python scripts/build_bbp.py --file <json> --source <name>   # offline/test
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

LISTS_DIR = Path(__file__).resolve().parent.parent / "lists"
BBP_FILE = LISTS_DIR / "bbp.txt"
EXCLUDE_FILE = LISTS_DIR / "exclude.txt"

SOURCES = {
    "hackerone": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/hackerone_data.json",
    "bugcrowd": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/bugcrowd_data.json",
    "yeswehack": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/yeswehack_data.json",
    "immunefi": ("https://raw.githubusercontent.com/infosec-us-team/"
                 "Immunefi-Bug-Bounty-Programs-Unofficial/refs/heads/main/projects.json"),
}

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
    "issues", "watching", "custom-infra",
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


STRONG_KEYS = {"in_scope", "assets"}
# programs explicitly exclude these orgs from scope: never scan them
FORBIDDEN_KEYS = {"out_of_scope"}


def _strings_with_strength(node, strong=False, forbidden=False):
    """Yield (text, strong, forbidden); only in_scope/assets strings are
    strong, and anything under out_of_scope is skipped entirely."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings_with_strength(
                value,
                strong or key in STRONG_KEYS,
                forbidden or key in FORBIDDEN_KEYS,
            )
    elif isinstance(node, list):
        for value in node:
            yield from _strings_with_strength(value, strong, forbidden)
    elif isinstance(node, str):
        yield node, strong, forbidden


def extract_handles(programs) -> tuple[set, set]:
    """(strong, weak) GitHub handles. Strong: github.com appears in an
    in-scope asset (the program literally lists the org as scope). Weak:
    only mentioned in policy text — usually the company's org, sometimes
    project names or noise worth pruning by hand."""
    strong, weak, banned = set(), set(), set()
    for program in programs:
        for text, is_strong, is_forbidden in _strings_with_strength(program):
            for match in GITHUB_RE.finditer(text):
                handle = match.group(1).lower()
                if handle in RESERVED:
                    continue
                if is_forbidden:
                    banned.add(handle)
                else:
                    (strong if is_strong else weak).add(handle)
    # an org listed both in and out of scope (different programs, or
    # program-level exclusions) stays banned: respect the exclusion
    strong -= banned
    weak -= banned
    return strong, weak


def load(path_or_url):
    if path_or_url.startswith("http"):
        with urllib.request.urlopen(path_or_url) as resp:
            return json.loads(resp.read())
    return json.loads(Path(path_or_url).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="path to a single downloaded source json")
    parser.add_argument("--source", default="immunefi", choices=SOURCES,
                        help="which platform the --file belongs to")
    parser.add_argument("--weak", action="store_true",
                        help="also include policy-text-only mentions (noisy)")
    args = parser.parse_args()

    LISTS_DIR.mkdir(exist_ok=True)

    handles = {}
    weak_handles = {}
    if args.file:
        sources = {args.source: args.file}
    else:
        sources = SOURCES

    for platform, url in sources.items():
        print(f"[*] {platform}: downloading {url.rsplit('/', 1)[-1]}")
        try:
            programs = load(url)
        except Exception as e:
            print(f"[!] {platform}: failed to load ({e}); skipping")
            continue
        strong, weak = extract_handles(programs)
        handles[platform] = strong
        weak_handles[platform] = weak - strong
        print(f"[+] {platform}: {len(programs)} programs -> "
              f"{len(strong)} scope-listed + {len(weak - strong)} policy-only handles")

    excluded = set()
    if EXCLUDE_FILE.exists():
        excluded = {line.strip().lower() for line in EXCLUDE_FILE.read_text().splitlines()
                    if line.strip() and not line.startswith("#")}
        print(f"[*] excluding {len(excluded)} account(s) from {EXCLUDE_FILE}")

    legacy = set()
    if BBP_FILE.exists():
        legacy = {line.strip().lower() for line in BBP_FILE.read_text().splitlines()
                  if line.strip() and not line.startswith("#")}

    all_handles = set().union(*handles.values()) if handles else set()
    if args.weak:
        all_handles |= set().union(*weak_handles.values()) if weak_handles else set()

    merged = sorted((legacy | all_handles) - excluded)
    BBP_FILE.write_text("\n".join(merged) + "\n")

    print(f"[+] legacy entries:  {len(legacy)}")
    print(f"[+] new handles:     {len(all_handles - legacy)}")
    if not args.weak and weak_handles:
        pruned = sorted(set().union(*weak_handles.values()) - all_handles)
        print(f"[-] policy-only handles not added ({len(pruned)}; add --weak to include):")
        for handle in pruned:
            print(f"      {handle}")
    print(f"[+] wrote {len(merged)} accounts -> {BBP_FILE}")


if __name__ == "__main__":
    sys.exit(main())
