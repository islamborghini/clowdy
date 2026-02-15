"""
HTTP routes CRUD router.

Manages per-project route definitions that map HTTP method + path patterns
to functions. Routes are used by the gateway endpoint to dispatch incoming
HTTP requests to the correct function.

For example, a route like GET /users/:id tells the gateway: "when someone
sends GET /api/gateway/my-project/users/123, run the get_user function
and pass {id: '123'} as a path parameter."
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Function, Route
from app.routers.projects import _get_user_project
from app.schemas import RouteCreate, RouteResponse, RouteUpdate

router = APIRouter(prefix="/api/projects", tags=["routes"])

VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "ANY"}


def _validate_method(method: str) -> str:
    """Validate and normalize the HTTP method to uppercase."""
    method = method.upper()
    if method not in VALID_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method '{method}'. Must be one of: {', '.join(sorted(VALID_METHODS))}",
        )
    return method


def _validate_path(path: str) -> str:
    """Validate and normalize the route path (ensure leading slash, strip trailing)."""
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


@router.get("/{project_id}/routes", response_model=list[RouteResponse])
async def list_routes(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all routes for a project."""
    await _get_user_project(db, project_id, user_id)
    result = await db.execute(
        select(Route)
        .where(Route.project_id == project_id)
        .order_by(Route.path, Route.method)
    )
    return result.scalars().all()


@router.post("/{project_id}/routes", response_model=RouteResponse)
async def create_route(
    project_id: str,
    data: RouteCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new route mapping for a project."""
    await _get_user_project(db, project_id, user_id)

    method = _validate_method(data.method)
    path = _validate_path(data.path)

    # Verify the function exists and belongs to this project
    fn = await db.get(Function, data.function_id)
    if not fn or fn.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail="Function not found in this project",
        )

    # Check for duplicate route (same method + path in this project)
    existing = await db.execute(
        select(Route).where(
            Route.project_id == project_id,
            Route.method == method,
            Route.path == path,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Route {method} {path} already exists in this project",
        )

    route = Route(
        project_id=project_id,
        function_id=data.function_id,
        method=method,
        path=path,
        description=data.description,
    )
    db.add(route)
    await db.commit()
    await db.refresh(route)
    return route


@router.put("/{project_id}/routes/{route_id}", response_model=RouteResponse)
async def update_route(
    project_id: str,
    route_id: str,
    data: RouteUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing route."""
    await _get_user_project(db, project_id, user_id)

    route = await db.get(Route, route_id)
    if not route or route.project_id != project_id:
        raise HTTPException(status_code=404, detail="Route not found")

    updates = data.model_dump(exclude_unset=True)

    if "method" in updates:
        updates["method"] = _validate_method(updates["method"])
    if "path" in updates:
        updates["path"] = _validate_path(updates["path"])
    if "function_id" in updates:
        fn = await db.get(Function, updates["function_id"])
        if not fn or fn.project_id != project_id:
            raise HTTPException(
                status_code=400,
                detail="Function not found in this project",
            )

    for field, value in updates.items():
        setattr(route, field, value)

    await db.commit()
    await db.refresh(route)
    return route


@router.delete("/{project_id}/routes/{route_id}")
async def delete_route(
    project_id: str,
    route_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a route."""
    await _get_user_project(db, project_id, user_id)

    route = await db.get(Route, route_id)
    if not route or route.project_id != project_id:
        raise HTTPException(status_code=404, detail="Route not found")

    await db.delete(route)
    await db.commit()
    return {"detail": "Route deleted"}
