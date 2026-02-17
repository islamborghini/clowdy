"""
Function invocation router.

This module handles the execution of user functions. When someone sends a POST
request to /api/invoke/{function_id}, we:

1. Look up the function's code in the database
2. Run it inside a Docker container (isolated from the host)
3. Save an invocation log (input, output, status, duration)
4. Return the function's output to the caller

This is the core of Clowdy - the part that makes it a real serverless platform.
Without this, functions are just stored code that doesn't do anything.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import EnvVar, Function, Invocation, Project
from app.schemas import InvokeRequest, InvocationResponse
from app.services.docker_runner import run_function
from app.services.image_builder import get_image_name

router = APIRouter(prefix="/api", tags=["invoke"])


@router.post("/invoke/{function_id}")
async def invoke_function(
    function_id: str,
    request: InvokeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Invoke (run) a deployed function.

    This is what makes the platform work. The flow:
    1. Find the function by ID in the database
    2. Check it's in "active" status (not errored/disabled)
    3. Pass the code + input to the Docker runner
    4. Save an invocation log for history/debugging
    5. Return the result

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

    # Step 3: Fetch project env vars and custom image (if function belongs to a project)
    env_vars = None
    image_name = None
    if fn.project_id:
        ev_result = await db.execute(
            select(EnvVar).where(EnvVar.project_id == fn.project_id)
        )
        env_var_rows = ev_result.scalars().all()
        if env_var_rows:
            env_vars = {ev.key: ev.value for ev in env_var_rows}

        # Check if project has a custom image with pip dependencies
        project = await db.get(Project, fn.project_id)
        if project and project.requirements_hash:
            image_name = get_image_name(project.id, project.requirements_hash)

        # Inject DATABASE_URL if project has a Neon database
        if project and project.database_url:
            if env_vars is None:
                env_vars = {}
            env_vars["DATABASE_URL"] = project.database_url

    # Step 4: Run the code in a Docker container
    result = await run_function(
        code=fn.code,
        input_data=request.input,
        env_vars=env_vars,
        function_name=fn.name,
        image_name=image_name,
    )

    # Step 5: Save the invocation log
    invocation = Invocation(
        function_id=function_id,
        input=json.dumps(request.input),
        output=json.dumps(result["output"]) if isinstance(result["output"], dict) else str(result["output"]),
        status="success" if result["success"] else "error",
        duration_ms=result["duration_ms"],
    )
    db.add(invocation)
    await db.commit()
    await db.refresh(invocation)

    # Step 6: Return the result
    if not result["success"]:
        # Still return 200 but include the error in the response body.
        # This way the invocation log is saved even for failed runs.
        return {
            "success": False,
            "error": result["output"],
            "duration_ms": result["duration_ms"],
            "invocation_id": invocation.id,
        }

    return {
        "success": True,
        "output": result["output"],
        "duration_ms": result["duration_ms"],
        "invocation_id": invocation.id,
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
    # Verify the function exists
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")

    # Fetch invocations ordered by most recent first
    stmt = (
        select(Invocation)
        .where(Invocation.function_id == function_id)
        .order_by(Invocation.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
