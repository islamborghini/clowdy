"""
API Gateway router.

This is the core of Clowdy's backend deployment feature. It receives
external HTTP requests at /api/gateway/{project_slug}/{path} and routes
them to the appropriate function based on the project's route table.

For example, if project "my-api" has a route GET /users/:id mapped to
the get_user function, then:

    GET /api/gateway/my-api/users/123

will invoke get_user with an event containing:
    {"method": "GET", "path": "/users/123", "params": {"id": "123"}, ...}

The gateway is PUBLIC (no auth required). This is intentional -- these
are deployed endpoints meant to be called by external clients.
"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Function, FunctionVersion, Invocation, Project, Route
from app.services.context import resolve_context

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


def _path_pattern_to_regex(pattern: str) -> tuple[re.Pattern, list[str]]:
    """
    Convert a route path pattern like /users/:id/posts/:postId
    into a compiled regex with named groups and a list of param names.

    Examples:
        "/users/:id"  -> regex matching /users/123, extracts id="123"
        "/health"     -> regex matching exactly /health
    """
    param_names = []
    regex_parts = []
    for segment in pattern.split("/"):
        if not segment:
            continue
        if segment.startswith(":"):
            name = segment[1:]
            param_names.append(name)
            regex_parts.append(f"(?P<{name}>[^/]+)")
        else:
            regex_parts.append(re.escape(segment))

    regex_str = "^/" + "/".join(regex_parts) + "$"
    return re.compile(regex_str), param_names


def _match_route(
    routes: list[Route], method: str, request_path: str
) -> tuple[Route, dict[str, str]] | None:
    """
    Find the first route that matches the given HTTP method and path.

    Priority: exact method match first, then ANY (wildcard) method.
    Returns (matched_route, extracted_params) or None.
    """
    method = method.upper()

    # Normalize the path
    if not request_path.startswith("/"):
        request_path = "/" + request_path
    if len(request_path) > 1 and request_path.endswith("/"):
        request_path = request_path.rstrip("/")

    # Try exact method matches first, then ANY as fallback
    for check_method in [method, "ANY"]:
        for route in routes:
            if route.method != check_method:
                continue
            regex, _ = _path_pattern_to_regex(route.path)
            match = regex.match(request_path)
            if match:
                return route, match.groupdict()

    return None


async def _handle_gateway(
    project_slug: str,
    path: str,
    request: Request,
    db: AsyncSession,
):
    """
    Core gateway logic shared by both the path and root handlers.

    Steps:
    1. Resolve project by slug
    2. Load all routes for the project
    3. Match request method + path against route patterns
    4. Build an event object with full HTTP context
    5. Resolve execution context (env vars, image, DATABASE_URL)
    6. Run the matched function via InvokeService
    7. Log the invocation with gateway metadata
    8. Return the function's response
    """
    # Step 1: Resolve project by slug
    result = await db.execute(
        select(Project).where(Project.slug == project_slug)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Step 2: Load all routes for this project
    routes_result = await db.execute(
        select(Route).where(Route.project_id == project.id)
    )
    routes = routes_result.scalars().all()

    if not routes:
        raise HTTPException(
            status_code=404,
            detail="No routes configured for this project",
        )

    # Step 3: Match request against routes
    request_path = "/" + path if path else "/"
    match_result = _match_route(routes, request.method, request_path)
    if not match_result:
        raise HTTPException(
            status_code=404,
            detail=f"No route matches {request.method} {request_path}",
        )
    matched_route, path_params = match_result

    # Step 4: Fetch the function
    fn = await db.get(Function, matched_route.function_id)
    if not fn or fn.status != "active":
        raise HTTPException(
            status_code=503,
            detail="The function for this route is not available",
        )

    # Step 5: Build the event object
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            raw = await request.body()
            body = raw.decode("utf-8") if raw else None

    query_params = dict(request.query_params)

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "connection", "authorization", "content-length")
    }

    event = {
        "method": request.method,
        "path": request_path,
        "params": path_params,
        "query": query_params,
        "headers": headers,
        "body": body,
    }

    # Step 6: Resolve active version's code
    version = await db.get(FunctionVersion, (fn.id, fn.active_version))
    if not version:
        return JSONResponse(
            status_code=500,
            content={"error": "Active version not found"},
        )

    # Step 7: Resolve execution context (env vars, custom image, DATABASE_URL)
    ctx = await resolve_context(project.id, db)

    # Step 8: Run the function via InvokeService
    invoke_service = request.app.state.invoke_service
    result = await invoke_service.invoke(
        code=version.code,
        input_data=event,
        env_vars=ctx.env_vars,
        function_name=fn.name,
        image_name=ctx.image_name,
        network_enabled=fn.network_enabled,
    )

    # Step 8: Save invocation log with gateway metadata
    invocation = Invocation(
        function_id=fn.id,
        input=json.dumps(event),
        output=(
            json.dumps(result["output"])
            if isinstance(result["output"], dict)
            else str(result["output"])
        ),
        status="success" if result["success"] else "error",
        duration_ms=result["duration_ms"],
        source="gateway",
        http_method=request.method,
        http_path=request_path,
    )
    db.add(invocation)
    await db.commit()

    # Step 9: Build the HTTP response
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["output"])

    output = result["output"]

    # Support the full response contract: {statusCode, headers, body}
    # If the function returns this shape, use it to build the HTTP response.
    # Otherwise, auto-wrap the return value as 200 JSON.
    if isinstance(output, dict) and "statusCode" in output:
        status_code = output.get("statusCode", 200)
        resp_headers = output.get("headers", {})
        resp_body = output.get("body", None)
        return JSONResponse(
            content=resp_body,
            status_code=status_code,
            headers=resp_headers,
        )

    # Default: return as 200 JSON
    return output


@router.api_route(
    "/{project_slug}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def gateway_with_path(
    project_slug: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle gateway requests with a path (e.g., /api/gateway/my-project/users/123)."""
    return await _handle_gateway(project_slug, path, request, db)


@router.api_route(
    "/{project_slug}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def gateway_root(
    project_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle gateway requests to the project root (e.g., /api/gateway/my-project)."""
    return await _handle_gateway(project_slug, "", request, db)
