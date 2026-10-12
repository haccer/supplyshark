from . import registry, search, clean
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
import json
import random
import aiofiles
import asyncio

async def find_package_json(directory: str) -> list:
    packages = defaultdict(set)
    badvalues = ["workspace:",
                "file:",
                "npm:",
                "git+",
                "github:",
                "https://github",
                "./",
                "git://",
                "/",
                "link:"]

    async def process_file(file_path: Path) -> None:
        async with aiofiles.open(file_path, 'r') as f:
            try:
                data = json.loads(await f.read())
                for key in ('dependencies', 'devDependencies'):
                    if key in data:
                        dependencies = data.get(key, {})
                        for k, v in dependencies.items():
                            if not any(badvalue in v for badvalue in badvalues):
                                packages[key].add(k)
            except:
                print("[!] Invalid JSON. Skipping.")

    directory = Path(directory).resolve()
    tasks = [asyncio.create_task(process_file(file)) for file in directory.rglob('package.json') if file.is_file()]
    await asyncio.gather(*tasks)
    return list(packages['dependencies'].union(packages['devDependencies']))

def read_npm_search_json(path: str) -> list:
    matches = defaultdict(set)

    search_file = Path(path) / "npm_search.json"
    if not search_file.exists():
        return []

    with open(search_file, 'r', encoding='utf-8') as f:
        for line in f:
            match_dict = json.loads(line.strip())
            matches[match_dict['match']]

    matches_list = list(matches.keys())
    return clean.search(matches_list)

async def package_missing(package: str) -> bool:
    # Unscoped names historically allow uppercase spellings; check both the
    # literal and lowercased form so an existing package is never reported
    # as available just because the docs used different casing.
    names = {package}
    if package != package.lower():
        names.add(package.lower())
    for name in names:
        status = await registry.status(f"https://registry.npmjs.org/{quote(name, safe='')}")
        if status != 404:
            return False
    return True

async def scan_packages(path, package):
    if not await package_missing(package):
        return []

    results = [{"package": package}]
    data = await search.package_json_results(path, package)
    results.extend(json.loads(data))
    search_data = await search.package_search_json_results(f"{path}/npm_search.json", package)
    results.extend(search_data)

    if results == [{"package": package}]:
        results = []

    return results


_scope_cache = {}
_scope_status_cache = {}
_scope_notice_printed = False


async def scope_populated(scope_name: str) -> bool | None:
    """True if any public package exists under @scope. The registry search
    ignores the scope: qualifier, so hits are name-matched client-side."""
    if scope_name in _scope_cache:
        return _scope_cache[scope_name]

    data = await registry.get_json(
        f"https://registry.npmjs.org/-/v1/search?text=@{quote(scope_name)}&size=250")
    if data is None:
        return None

    prefix = f"@{scope_name.lower()}/"
    populated = any((obj.get("package") or {}).get("name", "").lower().startswith(prefix)
                    for obj in data.get("objects", []))
    _scope_cache[scope_name] = populated
    return populated


async def scope_status(name: str, probe_packages=()) -> str:
    """One verdict per npm scope: 'taken', 'available', or 'unknown'.

    Cheapest reliable proof first: any package under the scope existing on
    the registry means the scope is taken (plain registry API, no bot
    protection). The profile page (~name) is the authoritative signal in
    both directions — 200 means the account exists, 404 means claimable —
    but sits behind Cloudflare, so it runs after the probe. The search
    index is the last 'taken' fallback; otherwise 'unknown'.
    Verdicts are memoized per run; underlying statuses disk-cached."""
    global _scope_notice_printed
    key = name.lower()
    if key in _scope_status_cache:
        return _scope_status_cache[key]

    for probe in sorted(probe_packages)[:3]:
        if not await package_missing(probe):
            _scope_status_cache[key] = "taken"
            return "taken"

    code = await registry.status(f"https://www.npmjs.com/~{quote(name)}", browser=True)
    if code in (401, 403):
        # Cloudflare challenges individual lookups transiently; a spaced
        # retry turns most of them into real answers
        await asyncio.sleep(2 + random.uniform(0, 2))
        code = await registry.status(f"https://www.npmjs.com/~{quote(name)}", browser=True)
    if code == 200:
        verdict = "taken"
    elif code == 404:
        verdict = "available"
    else:
        if await scope_populated(name):
            verdict = "taken"
        else:
            if code in (401, 403) and not _scope_notice_printed:
                print("[!] npm scope owner page blocked (bot protection); "
                      "some scopes reported as unverified.")
                _scope_notice_printed = True
            verdict = "unknown"

    _scope_status_cache[key] = verdict
    return verdict


async def scope_check(path, scope, packages):
    """Scope-level shortcut: if the scope is taken, no package under it is
    claimable (skip them all); if available, one finding covers every
    package under it; unknown reports a single unverified finding."""
    name = scope.split('@')[1].split('/')[0]
    verdict = await scope_status(name, probe_packages=packages)
    if verdict == "taken":
        return []

    refs = []
    for package in packages:
        data = await search.package_json_results(path, package)
        refs.extend(json.loads(data))
        stream = await search.package_search_json_results(f"{path}/npm_search.json", package)
        refs.extend(stream)

    if not refs:
        return []  # scope referenced nowhere scannable

    finding = {"scope": scope, "packages": sorted(packages)}
    if verdict == "unknown":
        finding["unverified"] = True
    return [finding] + refs


