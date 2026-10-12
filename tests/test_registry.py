"""Rate-limit handling in the shared registry layer: retries, backoff,
caching. The HTTP transport itself is faked via registry._request."""
import asyncio
import json

import pytest

from shark import registry


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Isolated cache file, tiny backoff, fresh state."""
    monkeypatch.setattr(registry, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(registry, "RETRY_BASE_DELAY", 0.001)
    registry.reset()
    yield
    registry.reset()


def _responses(seq):
    """Fake _request that replays a scripted sequence of status codes."""
    calls = {"n": 0}

    async def fake_request(url, browser=False):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i], None

    return fake_request, calls


async def test_retry_then_success(isolated, monkeypatch):
    fake, calls = _responses([429, 200])
    monkeypatch.setattr(registry, "_request", fake)

    assert await registry.status("https://example.test/a") == 200
    assert calls["n"] == 2


async def test_retry_gives_up_after_max_attempts(isolated, monkeypatch):
    fake, calls = _responses([429])
    monkeypatch.setattr(registry, "_request", fake)

    assert await registry.status("https://example.test/a") == 429
    assert calls["n"] == registry.MAX_ATTEMPTS


async def test_5xx_is_retryable(isolated, monkeypatch):
    fake, calls = _responses([503, 404])
    monkeypatch.setattr(registry, "_request", fake)

    assert await registry.status("https://example.test/a") == 404
    assert calls["n"] == 2


async def test_non_retryable_not_retried(isolated, monkeypatch):
    fake, calls = _responses([403])
    monkeypatch.setattr(registry, "_request", fake)

    assert await registry.status("https://example.test/a") == 403
    assert calls["n"] == 1


async def test_transport_error_returns_none(isolated, monkeypatch):
    async def fake(url, browser=False):
        return None, None

    monkeypatch.setattr(registry, "_request", fake)
    assert await registry.status("https://example.test/a") is None


async def test_definitive_answers_are_cached(isolated, monkeypatch):
    fake, calls = _responses([404])
    monkeypatch.setattr(registry, "_request", fake)

    assert await registry.status("https://example.test/pkg") == 404
    assert await registry.status("https://example.test/pkg") == 404
    assert calls["n"] == 1


async def test_rate_limited_answers_are_not_cached(isolated, monkeypatch):
    fake, calls = _responses([429, 429, 429, 200])
    monkeypatch.setattr(registry, "_request", fake)

    await registry.status("https://example.test/pkg")  # 429 after retries
    assert await registry.status("https://example.test/pkg") == 200
    assert calls["n"] == 4  # second call hit the network again


async def test_close_persists_cache(isolated, monkeypatch):
    fake, _ = _responses([200])
    monkeypatch.setattr(registry, "_request", fake)

    await registry.status("https://example.test/pkg")
    await registry.close()

    saved = json.loads(registry.CACHE_FILE.read_text())
    assert "https://example.test/pkg" in saved


async def test_concurrency_is_capped(isolated, monkeypatch):
    """No more than MAX_CONCURRENCY requests are in flight at once."""
    in_flight = {"now": 0, "peak": 0}

    async def fake(url, browser=False):
        in_flight["now"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["now"])
        await asyncio.sleep(0.01)
        in_flight["now"] -= 1
        return 200, None

    monkeypatch.setattr(registry, "_request", fake)
    monkeypatch.setattr(registry, "MAX_CONCURRENCY", 4)

    results = await asyncio.gather(*[registry.status(f"https://example.test/{i}") for i in range(20)])
    assert all(code == 200 for code in results)
    assert in_flight["peak"] <= 4
