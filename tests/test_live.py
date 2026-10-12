"""Opt-in smoke tests against the real registries (6 requests total).

Default runs skip these; run explicitly with:

    pytest -m live
"""
import pytest

from shark import gem, npm, pip, registry

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
async def _close_session():
    """The shared registry session binds to this test's event loop; drop it
    so the next test starts fresh instead of touching a closed loop."""
    registry.reset()
    yield
    await registry.close()
    registry.reset()


async def test_pypi_live():
    assert await pip.package_missing("requests") is False
    assert await pip.package_missing("definitely-not-a-real-pkg-xyz-123") is True


async def test_npm_live():
    assert await npm.package_missing("express") is False
    assert await npm.package_missing("definitely-not-a-real-pkg-xyz-123") is True


async def test_rubygems_live():
    assert await gem.gem_missing("rails") is False
    assert await gem.gem_missing("definitely-not-a-real-gem-xyz-123") is True
