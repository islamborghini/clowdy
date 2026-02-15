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

from app.database import get_db
from app.models import Function
from app.schemas import FunctionCreate, FunctionResponse, FunctionUpdate

# Create a router with a URL prefix. All routes in this file will start
# with "/api/functions". The "tags" group these endpoints together in the
# auto-generated docs at /docs.
router = APIRouter(prefix="/api/functions", tags=["functions"])


@router.post("", response_model=FunctionResponse)
async def create_function(data: FunctionCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new serverless function.

    FastAPI automatically parses the JSON request body into a FunctionCreate
    object. If required fields are missing or have wrong types, FastAPI
    returns a 422 Validation Error before this code even runs.
    """
    fn = Function(
        name=data.name,
        description=data.description,
        code=data.code,
        runtime=data.runtime,
    )
    db.add(fn)  # Stage the new row for insertion
    await db.commit()  # Write it to the database
    await db.refresh(fn)  # Reload from DB to get generated fields (id, timestamps)
    return fn


@router.get("", response_model=list[FunctionResponse])
async def list_functions(db: AsyncSession = Depends(get_db)):
    """List all functions, newest first."""
    result = await db.execute(select(Function).order_by(Function.created_at.desc()))
    # .scalars() extracts the Function objects from the result rows
    # .all() collects them into a list
    return result.scalars().all()


@router.get("/{function_id}", response_model=FunctionResponse)
async def get_function(function_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single function by its ID."""
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")
    return fn


@router.put("/{function_id}", response_model=FunctionResponse)
async def update_function(
    function_id: str, data: FunctionUpdate, db: AsyncSession = Depends(get_db)
):
    """
    Update an existing function. Only provided fields are changed.

    model_dump(exclude_unset=True) returns only the fields the client
    actually sent. For example, if the client sends {"name": "new_name"},
    we only update the name - code and description stay unchanged.
    """
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")

    # Loop through each provided field and update the model attribute
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(fn, field, value)

    await db.commit()
    await db.refresh(fn)
    return fn


@router.delete("/{function_id}")
async def delete_function(function_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a function by its ID."""
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")
    await db.delete(fn)
    await db.commit()
    return {"detail": "Function deleted"}
