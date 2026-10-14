#!/usr/bin/env bash
# verify_npm_exec_paths.sh — measure which execution paths a local JS
# package-manager client actually honors, against the fake registry.
# Run this whenever a new npm/pnpm/yarn version drops, then paste the
# table into AGENTS.md ("npm exec paths & severity").
#
# Everything is localhost + temp dirs; no real registry is contacted and
# nothing is published. Educational / authorized-testing use only.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8121}"
WORK="$(mktemp -d /tmp/npm-exec-probe.XXXXXX)"
MARKER="$WORK/marker.txt"
SRV_PID=""

cleanup() { [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

python3 "$HERE/fake_registry.py" --port "$PORT" --marker-file "$MARKER" \
    > "$WORK/server.log" 2>&1 &
SRV_PID=$!
sleep 1.5
if ! kill -0 "$SRV_PID" 2>/dev/null; then
    echo "[!] fake registry failed to start:"; cat "$WORK/server.log"; exit 1
fi
REG="http://127.0.0.1:$PORT"

client="${CLIENT:-npm}"
ver=$("$client" --version 2>/dev/null || echo "?")
node_ver=$(node --version 2>/dev/null || echo "?")

fresh_victim() { # $1 = dir name
    local dir="$WORK/$1"; mkdir -p "$dir"; cd "$dir"
    printf '{"name":"victim","private":true}\n' > package.json
    echo "registry=$REG/" > .npmrc
    rm -f "$MARKER"
}

echo "## Exec-path matrix — $client $ver (node $node_ver), $(date -u +%Y-%m-%d)"
echo "| Path | Result |"
echo "|---|---|"

# 1. plain install, default config -> does preinstall run?
fresh_victim install_default
if env POC_MARKER="$MARKER" "$client" install probe-install-default \
        --no-audit --no-fund > "$WORK/install_default.out" 2>&1 && [ -s "$MARKER" ]; then
    echo "| \`$client install <pkg>\` (default) → preinstall | RUNS |"
else
    echo "| \`$client install <pkg>\` (default) → preinstall | no |"
fi
BINLINK="no"; [ -e node_modules/.bin/probe-install-default ] && BINLINK="yes"
echo "| bin links created | $BINLINK |"

# 2. npx fetch-and-run
fresh_victim npx_fetch
if env POC_MARKER="$MARKER" npx --yes --registry="$REG" probe-npx-runner \
        > "$WORK/npx_fetch.out" 2>&1 && [ -s "$MARKER" ]; then
    echo "| \`npx --yes <pkg>\` (fetch-and-run) | RUNS |"
else
    echo "| \`npx --yes <pkg>\` (fetch-and-run) | no |"
fi

# 3. import-time execution of an installed dependency
fresh_victim import_dep
env POC_MARKER="$MARKER" "$client" install probe-import-dep \
    --no-audit --no-fund > /dev/null 2>&1
rm -f "$MARKER"
env POC_MARKER="$MARKER" node -e "require('probe-import-dep')" \
    > "$WORK/import_dep.out" 2>&1
if [ -s "$MARKER" ]; then
    echo "| installed dep → \`require()\` (import-time) | RUNS |"
else
    echo "| installed dep → \`require()\` (import-time) | no |"
fi

echo
echo "Raw outputs were under $WORK (removed on exit). Inspect for client
advisories, e.g. npm's 'install-scripts' warning naming the package and
script — that text is itself report evidence of the advisory-only state."
