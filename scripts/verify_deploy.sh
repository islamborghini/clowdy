#!/usr/bin/env bash
#
# Prove a Clowdy deployment actually works, from outside it.
#
#   ./scripts/verify_deploy.sh http://your-server-ip
#
# Checks behaviour, not just liveness. A 200 from the frontend says nothing
# about whether functions execute, whether the fleet registered, or whether
# the read-only demo is actually read-only -- and on a public box that last
# one matters most.
#
# Exits non-zero if anything fails, so it can gate a deploy.

set -uo pipefail

BASE="${1:-http://localhost}"
BASE="${BASE%/}"
PASS=0
FAIL=0

ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL + 1)); }

get()  { curl -fsS --max-time 30 "$BASE$1" 2>/dev/null; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$@" 2>/dev/null; }

# Both arguments are required. An inline default here would need braces
# inside a ${...} expansion, which bash splits at the first unescaped brace.
invoke() {
  curl -fsS --max-time 60 -X POST "$BASE/api/invoke/$1" \
    -H 'Content-Type: application/json' -d "$2" 2>/dev/null
}

printf '\nVerifying %s\n\n' "$BASE"

# 1. The page a visitor actually loads.
if get / | grep -q '<div id="root">'; then
  ok "frontend serves the app shell"
else
  bad "frontend did not serve the app shell"
fi

# 2. API reachable through the frontend's proxy, which is the path the browser
#    uses. Hitting the control plane directly would not prove the proxy works.
HEALTH="$(get /api/health || true)"
if echo "$HEALTH" | grep -q '"status":"ok"'; then
  ok "API reachable through the frontend proxy"
else
  bad "API not reachable through the frontend proxy"
fi

if echo "$HEALTH" | grep -q '"demo_mode":true'; then
  ok "running in read-only demo mode"
else
  bad "DEMO_MODE is off -- a public box would accept writes"
fi

# 3. The fleet registered itself.
CLUSTER="$(get /api/cluster || true)"
if echo "$CLUSTER" | grep -q '"mode": *"distributed"'; then
  ok "workers registered (distributed mode)"
else
  bad "no workers registered -- running single-node or Redis is down"
fi

# 4. Code actually executes. This is the one that matters.
FIRST="$(invoke demo-fib '{"input":{"n":90}}' || true)"
if echo "$FIRST" | grep -q '"success":true'; then
  ok "function executed"
else
  bad "function did not execute: ${FIRST:-no response}"
fi

# 5. The warm path. A second call must reuse the container the first left.
SECOND="$(invoke demo-fib '{"input":{"n":90}}' || true)"
if echo "$SECOND" | grep -q '"cold_start":false'; then
  ok "warm container reused on the second call"
else
  bad "second call still cold -- the pool is not being reused"
fi

# 6. Gateway routing with a path parameter.
if get /api/gateway/demo/echo/42 | grep -q '"id": *"42"'; then
  ok "gateway routed and extracted a path parameter"
else
  bad "gateway route did not resolve"
fi

# 7. The security boundary. Public host, so this is not optional.
WRITE="$(code -X POST "$BASE/api/functions" -H 'Content-Type: application/json' -d '{}')"
if [ "$WRITE" = "403" ]; then
  ok "writes are blocked (POST /api/functions -> 403)"
else
  bad "writes are NOT blocked (POST /api/functions -> $WRITE)"
fi

CHAT="$(code -X POST "$BASE/api/chat" -H 'Content-Type: application/json' -d '{}')"
if [ "$CHAT" = "403" ]; then
  ok "AI assistant is blocked (it can create and delete functions)"
else
  bad "AI assistant is NOT blocked (POST /api/chat -> $CHAT)"
fi

printf '\n%d passed, %d failed\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
