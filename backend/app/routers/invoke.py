"""
Function invocation router.

This module handles the execution of user functions. When someone sends a POST
request to /api/invoke/{function_id}, we:

1. Look up the function's code in the database
2. Resolve the execution context (env vars, image, DATABASE_URL)
3. Delegate to the Invoke Service (which manages warm/cold containers)
4. Save an invocation log (input, output, status, duration)
5. Return the function's output to the caller

This is the core of Clowdy - the part that makes it a real serverless platform.
Without this, functions are just stored code that doesn't do anything.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Function, Invocation
from app.schemas import InvokeRequest, InvocationResponse
from app.services.context import resolve_context

router = APIRouter(prefix="/api", tags=["invoke"])


@router.post("/invoke/{function_id}")
async def invoke_function(
    function_id: str,
    body: InvokeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Invoke (run) a deployed function.

    This is what makes the platform work. The flow:
    1. Find the function by ID in the database
    2. Check it's in "active" status (not errored/disabled)
    3. Resolve execution context (env vars, image, DATABASE_URL)
    4. Delegate to InvokeService (warm/cold container path)
    5. Save an invocation log for history/debugging
    6. Return the result

    Example request:
        POST /api/invoke/abc123
        Body: {"input": {"name": "Islam"}}

    Example response (success):
        {"output": {"message": "Hello, Islam!"}, "duration_ms": 342}

    Example response (error):
        {"detail": "Function error: NameError: name 'x' is not defined"}
    """
    # Step 1: Look up the function
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")

    # Step 2: Check status
    if fn.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Function is not active (status: {fn.status})",
        )

    # Step 3: Resolve execution context (env vars, custom image, DATABASE_URL)
    ctx = await resolve_context(fn.project_id, db)

    # Step 4: Run via InvokeService (handles warm/cold container path)
    invoke_service = request.app.state.invoke_service
    result = await invoke_service.invoke(
        code=fn.code,
        input_data=body.input,
        env_vars=ctx.env_vars,
        function_name=fn.name,
        image_name=ctx.image_name,
        network_enabled=fn.network_enabled,
    )

    # Step 5: Save the invocation log
    invocation = Invocation(
        function_id=function_id,
        input=json.dumps(body.input),
        output=json.dumps(result["output"]) if isinstance(result["output"], dict) else str(result["output"]),
        status="success" if result["success"] else "error",
        duration_ms=result["duration_ms"],
    )
    db.add(invocation)
    await db.commit()
    await db.refresh(invocation)

    # Step 6: Return the result
    if not result["success"]:
        return {
            "success": False,
            "error": result["output"],
            "duration_ms": result["duration_ms"],
            "invocation_id": invocation.id,
            "cold_start": result.get("cold_start", True),
        }

    return {
        "success": True,
        "output": result["output"],
        "duration_ms": result["duration_ms"],
        "invocation_id": invocation.id,
        "cold_start": result.get("cold_start", True),
    }


@router.get(
    "/functions/{function_id}/invocations",
    response_model=list[InvocationResponse],
)
async def list_invocations(
    function_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    List all invocation logs for a specific function, newest first.

    This powers the "Invocation Logs" section on the function detail page.
    Each log shows what input was sent, what output came back, whether it
    succeeded, and how long it took.
    """
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")

    stmt = (
        select(Invocation)
        .where(Invocation.function_id == function_id)
        .order_by(Invocation.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
