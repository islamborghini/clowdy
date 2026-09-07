"""
Functions CRUD router.

Handles creating, reading, updating, and deleting serverless functions.
All endpoints are prefixed with /api/functions.

Key FastAPI concepts used here:
- APIRouter: groups related endpoints together (like a mini-app)
- Depends(get_db): injects a database session into each request handler
- response_model: tells FastAPI what shape the response JSON should be
- HTTPException: returns an error response (e.g., 404 Not Found)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Function, FunctionVersion
from app.schemas import (
    FunctionCreate,
    FunctionResponse,
    FunctionUpdate,
    FunctionVersionResponse,
)

# Create a router with a URL prefix. All routes in this file will start
# with "/api/functions". The "tags" group these endpoints together in the
# auto-generated docs at /docs.
router = APIRouter(prefix="/api/functions", tags=["functions"])


async def _resolve_code(fn: Function, db: AsyncSession) -> str:
    """Fetch the code for a function's active version."""
    version = await db.get(FunctionVersion, (fn.id, fn.active_version))
    return version.code if version else ""


def _fn_response(fn: Function, code: str) -> dict:
    """Build a FunctionResponse-compatible dict with versioned code."""
    return {
        "id": fn.id,
        "name": fn.name,
        "description": fn.description,
        "code": code,
        "active_version": fn.active_version,
        "runtime": fn.runtime,
        "status": fn.status,
        "network_enabled": fn.network_enabled,
        "created_at": fn.created_at,
        "updated_at": fn.updated_at,
    }


@router.post("", response_model=FunctionResponse)
async def create_function(
    data: FunctionCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new serverless function.

    FastAPI automatically parses the JSON request body into a FunctionCreate
    object. If required fields are missing or have wrong types, FastAPI
    returns a 422 Validation Error before this code even runs.
    """
    fn = Function(
        name=data.name,
        description=data.description,
        runtime=data.runtime,
        user_id=user_id,
        project_id=data.project_id,
        active_version=1,
    )
    db.add(fn)
    await db.flush()  # Generate fn.id before creating the version

    version = FunctionVersion(
        function_id=fn.id,
        version=1,
        code=data.code,
    )
    db.add(version)
    await db.commit()
    await db.refresh(fn)
    return _fn_response(fn, data.code)


@router.get("", response_model=list[FunctionResponse])
async def list_functions(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all functions for the authenticated user, newest first."""
    result = await db.execute(
        select(Function)
        .where(Function.user_id == user_id)
        .order_by(Function.created_at.desc())
    )
    functions = result.scalars().all()
    return [
        _fn_response(fn, await _resolve_code(fn, db)) for fn in functions
    ]


@router.get("/{function_id}", response_model=FunctionResponse)
async def get_function(
    function_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single function by its ID. Must belong to the authenticated user."""
    fn = await db.get(Function, function_id)
    if not fn or fn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Function not found")
    code = await _resolve_code(fn, db)
    return _fn_response(fn, code)


@router.put("/{function_id}", response_model=FunctionResponse)
async def update_function(
    function_id: str,
    data: FunctionUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing function. Only provided fields are changed.

    model_dump(exclude_unset=True) returns only the fields the client
    actually sent. For example, if the client sends {"name": "new_name"},
    we only update the name - code and description stay unchanged.
    """
    fn = await db.get(Function, function_id)
    if not fn or fn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Function not found")

    updates = data.model_dump(exclude_unset=True)
    new_code = updates.pop("code", None)

    # Update non-code fields on the function
    for field, value in updates.items():
        setattr(fn, field, value)

    # If code changed, create a new version
    if new_code is not None:
        new_version_num = fn.active_version + 1
        version = FunctionVersion(
            function_id=fn.id,
            version=new_version_num,
            code=new_code,
        )
        db.add(version)
        fn.active_version = new_version_num

    await db.commit()
    await db.refresh(fn)
    code = await _resolve_code(fn, db)
    return _fn_response(fn, code)


@router.get("/{function_id}/versions", response_model=list[FunctionVersionResponse])
async def list_versions(
    function_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all versions for a function, newest first."""
    fn = await db.get(Function, function_id)
    if not fn or fn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Function not found")

    result = await db.execute(
        select(FunctionVersion)
        .where(FunctionVersion.function_id == function_id)
        .order_by(FunctionVersion.version.desc())
    )
    return result.scalars().all()


@router.put("/{function_id}/versions/{version}", response_model=FunctionResponse)
async def set_active_version(
    function_id: str,
    version: int,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a specific version as the active version."""
    fn = await db.get(Function, function_id)
    if not fn or fn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Function not found")

    fv = await db.get(FunctionVersion, (function_id, version))
    if not fv:
        raise HTTPException(status_code=404, detail="Version not found")

    fn.active_version = version
    await db.commit()
    await db.refresh(fn)
    return _fn_response(fn, fv.code)


@router.delete("/{function_id}")
async def delete_function(
    function_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a function by its ID. Must belong to the authenticated user."""
    fn = await db.get(Function, function_id)
    if not fn or fn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Function not found")
    await db.delete(fn)
    await db.commit()
    return {"detail": "Function deleted"}
