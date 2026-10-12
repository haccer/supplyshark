"""Shared HTTP helpers for registry lookups.

All availability checks go through one aiohttp session so connections are
reused, with three protections against API rate limits:

- a process-wide concurrency cap (MAX_CONCURRENCY)
- retry with exponential backoff on 429/5xx, honoring Retry-After
- a TTL disk cache so repeated scans of the same accounts don't re-query

Callers must treat only explicit 404 as "name is available"; anything
else (200, 401, 403, 429, 5xx, None) means taken or unknown, which keeps
the scanner conservative rather than reporting false positives. Only
definitive 200/404 responses are cached, so a rate-limited or failed
lookup never poisons later runs.
"""
import aiohttp
import asyncio
import json
import random
import time
from os import getenv
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HEADERS = {"User-Agent": "supplyshark (+https://github.com/haccer/supplyshark)"}
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
TIMEOUT = aiohttp.ClientTimeout(total=30)

# Optional: npm raises per-IP rate limits substantially for authenticated
# requests, which matters on mass scans.
NPM_TOKEN = getenv("NPM_TOKEN")


def _headers_for(url, browser):
    headers = dict(BROWSER_HEADERS if browser else HEADERS)
    if NPM_TOKEN and url.startswith("https://registry.npmjs.org/"):
        headers["Authorization"] = f"Bearer {NPM_TOKEN}"
    return headers

MAX_CONCURRENCY = 10
MAX_ATTEMPTS = 3
RETRYABLE = {429, 500, 502, 503, 504}
RETRY_BASE_DELAY = 1.0  # seconds; doubles per attempt, plus jitter
CACHE_TTL = 30 * 24 * 3600
CACHE_FILE = Path("/tmp/.supplyshark/registry-cache.json")

_session = None
_semaphore = None
_cache = None


def _load_cache():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            _cache = {url: (code, ts) for url, (code, ts) in json.load(f).items()}
    except (OSError, ValueError):
        _cache = {}
    now = time.time()
    _cache = {url: entry for url, entry in _cache.items() if now - entry[1] < CACHE_TTL}
    return _cache


def _save_cache():
    if _cache is None:
        return
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(_cache, f)
        tmp.replace(CACHE_FILE)
    except OSError:
        pass


async def _request(url, browser):
    """Single GET attempt; returns (status, retry_after_seconds)."""
    global _session
    try:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(timeout=TIMEOUT)
        headers = _headers_for(url, browser)
        async with _session.get(url, headers=headers) as resp:
            retry_after = None
            if resp.status == 429:
                try:
                    retry_after = float(resp.headers.get("Retry-After"))
                except (TypeError, ValueError):
                    retry_after = None
            return resp.status, retry_after
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return None, None


async def status(url, browser=False):
    """GET a URL and return the HTTP status code, or None on error."""
    cache = _load_cache()
    if url in cache:
        return cache[url][0]

    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    code = None
    for attempt in range(MAX_ATTEMPTS):
        async with _semaphore:
            code, retry_after = await _request(url, browser)
        if code not in RETRYABLE:
            break
        if attempt < MAX_ATTEMPTS - 1:
            delay = max(RETRY_BASE_DELAY * (2 ** attempt), retry_after or 0)
            await asyncio.sleep(delay + random.uniform(0, 0.5))

    if code in (200, 404):
        cache[url] = (code, time.time())
    return code


async def get_json(url):
    """GET a URL through the shared session and parse JSON, or None.
    One retry after a pause — transient 429/5xx under scan load would
    otherwise read as 'no data'."""
    global _session, _semaphore
    for attempt in range(2):
        try:
            if _session is None or _session.closed:
                _session = aiohttp.ClientSession(timeout=TIMEOUT)
            if _semaphore is None:
                _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
            async with _semaphore:
                async with _session.get(url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status not in (429, 500, 502, 503, 504):
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
            pass
        if attempt == 0:
            await asyncio.sleep(RETRY_BASE_DELAY + random.uniform(0, 0.5))
    return None


async def domain_registered(apex: str) -> bool | None:
    """Registration status via RDAP (rdap.org bootstraps to the registry):
    True = registered, False = unregistered (claimable), None = unknown.
    NXDOMAIN alone doesn't prove claimability — a registered but
    undelegated domain cannot be taken over."""
    code = await status(f"https://rdap.org/domain/{apex}")
    if code == 200:
        return True
    if code == 404:
        return False
    return None


async def close():
    global _session, _semaphore
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
    # -l mode runs each account in a fresh event loop; a semaphore bound to
    # a dead loop would raise on the next account, so always start clean
    _semaphore = None
    _save_cache()


def reset():
    """Drop all cached/in-flight state (used by tests)."""
    global _session, _semaphore, _cache
    _session = None
    _semaphore = None
    _cache = None
