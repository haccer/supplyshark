"""scripts/fake_registry.py endpoint behavior — hermetic (stdlib only;
the ruby-backed gem endpoints are skipped when ruby is absent)."""
import io
import json
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fake_registry  # noqa: E402

HAS_RUBY = shutil.which("ruby") is not None


@pytest.fixture
def server(monkeypatch, tmp_path):
    """Server on an ephemeral port in a background thread."""
    from http.server import ThreadingHTTPServer
    fake_registry.State.marker_file = str(tmp_path / "marker.txt")
    fake_registry.State.gem_names = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), fake_registry.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    t.join(timeout=5)
    fake_registry._artifact_cache.clear()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read(), r.headers


def test_npm_packument_dynamic(server):
    status, body, _ = _get(f"{server}/any-random-name")
    assert status == 200
    doc = json.loads(body)
    assert doc["name"] == "any-random-name"
    assert fake_registry.VERSION in doc["versions"]
    assert doc["versions"][fake_registry.VERSION]["dist"]["tarball"].startswith("http://")


def test_npm_packument_carries_bin_and_scripts(server):
    """Fidelity regression: npm reads bin (linking) and scripts (the
    install-scripts flow) from the PACKUMENT. A version object without
    them silently disables both — this once inverted our read of npm 11
    script behavior."""
    _, body, _ = _get(f"{server}/fidelity-check")
    ver = json.loads(body)["versions"][fake_registry.VERSION]
    assert ver["bin"] == {"fidelity-check": "index.js"}
    assert "preinstall" in ver["scripts"]


def test_npm_packument_scoped(server):
    status, body, _ = _get(f"{server}/@fake-scope/thing")
    assert status == 200
    assert json.loads(body)["name"] == "@fake-scope/thing"


def test_npm_tarball_is_valid_package(server):
    _, body, _ = _get(f"{server}/__tarball/some-pkg")
    with tarfile.open(fileobj=io.BytesIO(body)) as tar:
        names = tar.getnames()
    assert "package/package.json" in names
    assert "package/index.js" in names


def test_npm_internal_routes_404(server):
    for path in ("/-", "/", "/__internal"):
        try:
            _get(f"{server}{path}")
            assert False, path
        except urllib.error.HTTPError as e:
            assert e.code == 404


def test_pypi_simple_hash_matches_sdist(server):
    _, page, _ = _get(f"{server}/simple/some-pkg/")
    href = page.decode().split('href="')[1].split('"')[0]
    sha = href.split("#sha256=")[1]
    _, sdist, _ = _get(f"{server}{href}")
    import hashlib
    assert hashlib.sha256(sdist).hexdigest() == sha
    # sdist carries the PEP 517 build declaration + executing setup.py
    with tarfile.open(fileobj=io.BytesIO(sdist)) as tar:
        names = tar.getnames()
        assert any(n.endswith("pyproject.toml") for n in names)
        assert any(n.endswith("setup.py") for n in names)


def test_pypi_normalized_names_share_artifact(server):
    """fake_pkg / fake-pkg / fake.pkg must resolve to one stable artifact
    so the served bytes always match the advertised hash."""
    _, page1, _ = _get(f"{server}/simple/fake-pkg/")
    _, page2, _ = _get(f"{server}/simple/fake_pkg/")
    href1 = page1.decode().split('href="')[1].split('"')[0].split("#")[0]
    href2 = page2.decode().split('href="')[1].split('"')[0].split("#")[0]
    _, a, _ = _get(f"{server}{href1}")
    _, b, _ = _get(f"{server}{href2}")
    assert a == b


@pytest.mark.skipif(not HAS_RUBY, reason="ruby not available")
def test_gem_specs_marshal_roundtrip(server):
    fake_registry.State.gem_names = ["rt-check"]  # specs index needs names
    _, body, _ = _get(f"{server}/specs.4.8.gz")
    out = subprocess.run(
        ["ruby", "-e",
         "require 'zlib'; require 'stringio'; require 'rubygems';" 
         "require 'rubygems/safe_marshal';"
         "d = STDIN.binmode.read;"
         "p Gem::SafeMarshal.safe_load(Zlib::GzipReader.new(StringIO.new(d)).read)"],
        input=body, capture_output=True, check=True)
    assert "rt-check" in out.stdout.decode()


def test_gem_index_without_names_404s(server):
    try:
        _get(f"{server}/specs.4.8.gz")
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_npm_payload_carries_marker_logic(server):
    """The generated index.js must reference the marker env vars — the
    payload contract the instructions document."""
    _, body, _ = _get(f"{server}/__tarball/marker-check")
    with tarfile.open(fileobj=io.BytesIO(body)) as tar:
        idx = tar.extractfile("package/index.js").read().decode()
    assert "POC_MARKER" in idx and "fake-registry" in idx


def test_custom_tarball_served_and_packument_uses_its_manifest(server, tmp_path):
    """--tarball NAME:=PATH: the researcher-built package (e.g. poc_packages
    npm pack output) is served verbatim, and the packument carries THAT
    manifest (bin/scripts fidelity), not the generated one."""
    import gzip as _gzip
    import io as _io
    # build a tiny npm-shaped tarball
    pkg = json.dumps({"name": "custom-check", "version": "9.9.9",
                      "bin": {"custom-check": "index.js"},
                      "scripts": {"preinstall": "node index.js"}}).encode()
    idx = b"#!/usr/bin/env node\nconsole.log('custom payload');\n"
    buf = _io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, data in (("package/package.json", pkg), ("package/index.js", idx)):
            ti = tarfile.TarInfo(path); ti.size = len(data)
            tar.addfile(ti, _io.BytesIO(data))
    tgz = tmp_path / "custom-check-9.9.9.tgz"
    tgz.write_bytes(buf.getvalue())
    fake_registry.State.custom_tarballs["custom-check"] = str(tgz)
    try:
        _, body, _ = _get(f"{server}/custom-check")
        ver = json.loads(body)["versions"]["9.9.9"]
        assert ver["bin"] == {"custom-check": "index.js"}
        assert "preinstall" in ver["scripts"]
        _, tb, _ = _get(f"{server}/__tarball/custom-check")
        assert tb == tgz.read_bytes()
    finally:
        fake_registry.State.custom_tarballs.clear()
