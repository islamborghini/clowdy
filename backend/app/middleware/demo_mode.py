"""
Read-only demo mode.

The public demo runs arbitrary Python for anyone who can reach it. Deployed
function endpoints are meant to be public -- that is the product -- but
letting a stranger create a function on the box is a different thing
entirely, and on a free-tier VM it ends as a crypto miner within days.

This is one middleware rather than a guard on each endpoint deliberately.
There are roughly twenty mutating routes across nine routers, and the failure
mode of the per-endpoint approach is not that today's guard is wrong, it is
that the router someone adds next month has no guard at all. Blocking by
method at the edge means a new route is locked down by default.

Two paths stay open because they are how a deployed function is called:

    POST /api/invoke/{id}     run a function
    ANY  /api/gateway/{slug}  the HTTP gateway

Note that /api/chat is NOT open. The AI assistant has create, update, and
delete tools, so leaving it writable would hand back everything this closes.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Prefixes that remain writable: invoking a function is a POST, and gateway
# routes can be any method.
EXECUTION_PREFIXES = ("/api/invoke/", "/api/gateway/")

MESSAGE = (
    "This is a read-only public demo. Browsing, invoking existing functions, "
    "and the cluster view all work; creating or editing is disabled. Run it "
    "yourself with `docker compose up` to get the full platform."
)


def is_blocked(method: str, path: str) -> bool:
    """True if this request would change state and demo mode forbids it."""
    if method.upper() not in MUTATING_METHODS:
        return False
    return not path.startswith(EXECUTION_PREFIXES)


async def demo_mode_middleware(request: Request, call_next):
    """Reject state-changing requests with 403 and an explanation."""
    if is_blocked(request.method, request.url.path):
        logger.info("Demo mode blocked %s %s", request.method, request.url.path)
        return JSONResponse(status_code=403, content={"detail": MESSAGE})
    return await call_next(request)
