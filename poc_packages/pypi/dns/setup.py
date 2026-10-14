# sdist build hook: pip executes this when installing from a source
# distribution (the pip-side equivalent of npm's preinstall).
from setuptools import setup

import payload  # noqa: E402  (runs the DNS canary at build time)

setup()
