#!/usr/bin/env bash
# README screenshots from a throwaway demo: a fresh database in a temporary
# directory, filled with made-up votes, so no real data ends up in a picture.
# Light and dark, phone-sized, at 2x.
#
# Needs an anika-blue binary, Chromium, Node.js, npm and curl. For example,
# from the repository root on a build host:
#
#   cargo build
#   nix shell nixpkgs#chromium nixpkgs#nodejs nixpkgs#curl \
#     -c tools/screenshots/run.sh
#
# Writes screenshot.png and screenshot-dark.png to assets/.

usage() {
  cat <<EOF2
Usage: $(basename "$0") [-o OUTDIR]

Environment:
  ANIKA_BLUE  the binary (default: target/debug/anika-blue, else PATH)
  CHROMIUM    the browser (default: chromium)
  PORT        the demo server's port (default: 15077)
EOF2
}

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP=""
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]
  then
    kill "$SERVER_PID" 2>/dev/null
  fi
  if [[ -n "$TMP" ]]
  then
    rm -rf "$TMP"
  fi
}

# vote JAR SHADE...: "yes" votes for each shade, as the visitor in JAR.
vote() {
  local jar="$1"
  local shade
  shift
  for shade in "$@"
  do
    curl -sf -b "$jar" -c "$jar" -o /dev/null \
      --data-urlencode "shade=$shade" -d vote=yes "$URL/vote" || return 1
  done
}

wait_for_server() {
  local _
  for _ in $(seq 50)
  do
    if curl -sf -o /dev/null "$URL/healthz"
    then
      return 0
    fi
    sleep 0.2
  done
  printf 'The demo server did not come up; see %s/server.log\n' "$TMP" >&2
  return 1
}

main() {
  local out="$ROOT/assets"

  while [[ -n "${1:-}" ]]
  do
    case "$1" in
      -h|--help)
        usage
        return 0
        ;;
      -o|--out)
        out="${2:?}"
        shift 2
        ;;
      *)
        usage >&2
        return 2
        ;;
    esac
  done

  PORT="${PORT:-15077}"
  # Playwright wants an absolute path.
  CHROMIUM="$(command -v "${CHROMIUM:-chromium}")" || return 1
  ANIKA_BLUE="${ANIKA_BLUE:-$ROOT/target/debug/anika-blue}"
  if [[ ! -x "$ANIKA_BLUE" ]]
  then
    ANIKA_BLUE="anika-blue"
  fi
  URL="http://127.0.0.1:$PORT"

  TMP="$(mktemp -d)" || return 1
  trap cleanup EXIT

  "$ANIKA_BLUE" --host 127.0.0.1 --port "$PORT" \
    --database "$TMP/demo.db" --secret-key demo > "$TMP/server.log" 2>&1 &
  SERVER_PID="$!"
  wait_for_server || return 1

  # Everyone else: three made-up visitors.
  vote "$TMP/a" "#1e4fd8" "#2563eb" "#3056c9" "#1d4ed8" || return 1
  vote "$TMP/b" "#0f6fd1" "#2a7de1" "#1565c0" || return 1
  vote "$TMP/c" "#3b5bdb" "#364fc7" "#4263eb" "#2b4acb" "#1c3fbf" || return 1

  mkdir -p "$out" "$TMP/pw" || return 1
  (
    cd "$TMP/pw" || exit 1
    npm init -y > /dev/null && npm install --silent playwright-core > /dev/null
  ) || return 1

  PLAYWRIGHT_DIR="$TMP/pw" OUT="$out" URL="$URL" CHROMIUM="$CHROMIUM" \
    node "$ROOT/tools/screenshots/shots.mjs"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]
then
  main "$@"
fi

# vim: set ft=sh et ts=2 sw=2 :
