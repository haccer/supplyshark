from . import registry, search, clean
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
import json
import re

def read_gem_search_json(path: str) -> list:
    matches = defaultdict(set)

    search_file = Path(path) / "gem_search.json"
    if not search_file.exists():
        return []

    with open(search_file, 'r', encoding='utf-8') as f:
        for line in f:
            match_dict = json.loads(line.strip())
            matches[match_dict['match']]

    matches_list = list(matches.keys())
    return clean.gem_search(matches_list)

async def gem_missing(gem: str) -> bool:
    names = {gem}
    if gem != gem.lower():
        names.add(gem.lower())
    for name in names:
        status = await registry.status(f"https://rubygems.org/api/v1/gems/{quote(name)}.json")
        if status != 404:
            return False
    return True

async def scan_gems(path, gem):
    if not await gem_missing(gem):
        return []

    results = [{"package": gem}]
    search_data = await search.package_search_json_results(f"{path}/gem_search.json", gem)
    results.extend(search_data)

    if results == [{"package": gem}]:
        results = []

    return results

def gem_files(gemfile):
    results = []
    with open(gemfile, "r", encoding="utf8", errors="ignore") as f:
        for line in f.readlines():
            pattern = re.compile(r'git: "https://github.com/(.*?)/+', re.IGNORECASE)
            result = pattern.findall(line)
            results += result

    return results
