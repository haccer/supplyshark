from . import clean, registry, search
from collections import defaultdict
from pathlib import Path
import aiofiles
import asyncio
import json
import re

# PEP 508 name: starts and ends alphanumeric, middle allows . _ -
REQ_NAME = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?')


def parse_requirement(line: str) -> str | None:
    """Extract a distribution name from a requirement line.

    Handles comments, option lines (-r/-e/--index-url), extras (pkg[extra]),
    version specifiers, environment markers (; python_version ...) and
    PEP 508 direct URL references (pkg @ https://...), which resolve
    directly and are therefore not registry-confusable.
    """
    line = line.strip()
    if not line or line.startswith('#') or line.startswith('-'):
        return None
    line = line.split('#')[0].split(';')[0]
    if ' @ ' in line:
        return None
    token = line.split()[0].split('[')[0]
    match = REQ_NAME.match(token)
    return match.group(0) if match else None


async def find_requirements_txt(directory: Path) -> list[str]:
    lines = []

    async def process_file(file_path: Path) -> None:
        async with aiofiles.open(file_path, 'r', errors='ignore') as f:
            async for line in f:
                name = parse_requirement(line)
                if name:
                    lines.append(name)

    directory = Path(directory).resolve()
    files = [file for file in directory.rglob('*.txt') if 'requirements' in file.name and file.is_file()]
    await asyncio.gather(*[process_file(file) for file in files])
    return lines


def find_pyproject_toml(directory) -> list[str]:
    """Collect declared dependencies from pyproject.toml files.

    Covers PEP 621 [project] dependencies/optional-dependencies and
    Poetry [tool.poetry.dependencies]. Git/path/url Poetry sources are
    skipped: they do not resolve from PyPI.
    """
    try:
        import tomllib
    except ImportError:
        print("[!] tomllib unavailable (Python < 3.11); skipping pyproject.toml parsing.")
        return []

    names = []

    for file in Path(directory).resolve().rglob('pyproject.toml'):
        try:
            with open(file, 'rb') as f:
                data = tomllib.load(f)
        except Exception:
            print("[!] Invalid pyproject.toml. Skipping.")
            continue

        project = data.get('project') or {}
        for dep in (project.get('dependencies') or []):
            name = parse_requirement(dep)
            if name:
                names.append(name)
        for group in (project.get('optional-dependencies') or {}).values():
            for dep in group:
                name = parse_requirement(dep)
                if name:
                    names.append(name)

        poetry_deps = ((data.get('tool') or {}).get('poetry') or {}).get('dependencies') or {}
        for name, spec in poetry_deps.items():
            if name == 'python':
                continue
            if isinstance(spec, dict) and any(k in spec for k in ('git', 'path', 'url', 'source')):
                continue
            parsed = parse_requirement(f"{name}{spec}" if isinstance(spec, str) else name)
            if parsed:
                names.append(parsed)

    return names


def read_pip_search_json(path: str) -> list:
    matches = defaultdict(set)

    search_file = Path(path) / "pip_search.json"
    if not search_file.exists():
        return []

    with open(search_file, 'r', encoding='utf-8') as f:
        for line in f:
            match_dict = json.loads(line.strip())
            matches[match_dict['match']]

    matches_list = list(matches.keys())
    return clean.search(matches_list)


def normalize_pypi(name: str) -> str:
    """PEP 503 normalization: pip resolves names case-insensitively with
    -, _ and . equivalent, so a collision under the normalized name blocks
    registration of the original spelling."""
    return re.sub(r'[-_.]+', '-', name.lower())


async def package_missing(package: str) -> bool:
    status = await registry.status(f"https://pypi.org/pypi/{normalize_pypi(package)}/json")
    return status == 404


async def scan_packages(path, package):
    if not package or not await package_missing(package):
        return []

    results = [{"package": package}]
    for glob in ('*requirements*.txt', 'pyproject.toml'):
        data = await search.dependency_file_results(path, package, '-g', glob)
        results.extend(json.loads(data))
    search_data = await search.package_search_json_results(f"{path}/pip_search.json", package)
    results.extend(search_data)

    if results == [{"package": package}]:
        results = []

    return results
