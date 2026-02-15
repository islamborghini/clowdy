"""
Chat router - AI agent endpoint.

This module provides the POST /api/chat endpoint where the frontend sends
user messages and receives AI responses. The key job of this router is to
connect the AI's tool calls to real database operations.

When the AI says "call create_function with name='greeter'", this router
actually creates the function in SQLite and runs it in Docker - the same
operations that happen when you use the UI directly.

Flow:
    1. Frontend sends: { messages: [{role: "user", content: "create a greeter"}] }
    2. This router passes the messages to the AI agent (Groq)
    3. The AI decides to call create_function tool
    4. execute_tool() runs the real database operation
    5. The result goes back to the AI
    6. The AI writes: "I've created your greeter function! ..."
    7. We return: { response: "...", tool_calls: [...] }
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Function, Invocation
from app.services.ai_agent import chat_with_tools
from app.services.docker_runner import run_function


router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    """
    What the frontend sends to the chat endpoint.

    messages is the full conversation history so the AI has context.
    Each message has a "role" (user or assistant) and "content" (the text).
    """

    messages: list[dict]


class ChatResponse(BaseModel):
    """What we send back to the frontend."""

    response: str
    tool_calls: list[dict] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Chat with the AI agent.

    The frontend sends the conversation history and we return the AI's response.
    If the AI calls any tools (create function, invoke, etc.), we execute them
    against the real database and include the results.
    """

    async def execute_tool(tool_name: str, tool_args: dict) -> dict:
        """
        Execute an AI tool call against the real database.

        This function maps tool names to actual database operations.
        It's passed to chat_with_tools() as a callback - when the AI says
        "call create_function", this function does the real work.
        """
        if tool_name == "create_function":
            return await _tool_create_function(db, tool_args)
        elif tool_name == "list_functions":
            return await _tool_list_functions(db)
        elif tool_name == "invoke_function":
            return await _tool_invoke_function(db, tool_args)
        elif tool_name == "view_logs":
            return await _tool_view_logs(db, tool_args)
        elif tool_name == "update_function":
            return await _tool_update_function(db, tool_args)
        elif tool_name == "delete_function":
            return await _tool_delete_function(db, tool_args)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    try:
        result = await chat_with_tools(
            messages=request.messages,
            execute_tool=execute_tool,
        )
        return ChatResponse(
            response=result["response"],
            tool_calls=result["tool_calls"],
        )
    except ValueError as exc:
        # Missing API key
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI agent error: {exc}",
        )


# --- Tool implementations ---
# Each function below implements one AI tool. They do the same database
# operations as the regular API endpoints (functions.py, invoke.py) but
# return simplified dicts that the AI can understand and relay to the user.


async def _tool_create_function(db: AsyncSession, args: dict) -> dict:
    """Create a new function in the database."""
    fn = Function(
        name=args["name"],
        description=args.get("description", ""),
        code=args["code"],
        runtime="python",
    )
    db.add(fn)
    await db.commit()
    await db.refresh(fn)
    return {
        "success": True,
        "function_id": fn.id,
        "name": fn.name,
        "invoke_url": f"/api/invoke/{fn.id}",
    }


async def _tool_list_functions(db: AsyncSession) -> dict:
    """List all functions."""
    stmt = select(Function).order_by(Function.created_at.desc())
    result = await db.execute(stmt)
    functions = result.scalars().all()

    if not functions:
        return {"functions": [], "message": "No functions deployed yet."}

    return {
        "functions": [
            {
                "id": fn.id,
                "name": fn.name,
                "description": fn.description,
                "status": fn.status,
                "runtime": fn.runtime,
            }
            for fn in functions
        ]
    }


async def _tool_invoke_function(db: AsyncSession, args: dict) -> dict:
    """Invoke a function in a Docker container."""
    fn = await db.get(Function, args["function_id"])
    if not fn:
        return {"error": f"Function '{args['function_id']}' not found"}

    if fn.status != "active":
        return {"error": f"Function is not active (status: {fn.status})"}

    input_data = args.get("input", {})
    result = await run_function(code=fn.code, input_data=input_data)

    # Save invocation log
    invocation = Invocation(
        function_id=fn.id,
        input=json.dumps(input_data),
        output=json.dumps(result["output"]) if isinstance(result["output"], dict) else str(result["output"]),
        status="success" if result["success"] else "error",
        duration_ms=result["duration_ms"],
    )
    db.add(invocation)
    await db.commit()

    return {
        "success": result["success"],
        "output": result["output"],
        "duration_ms": result["duration_ms"],
    }


async def _tool_view_logs(db: AsyncSession, args: dict) -> dict:
    """View recent invocation logs for a function."""
    fn = await db.get(Function, args["function_id"])
    if not fn:
        return {"error": f"Function '{args['function_id']}' not found"}

    stmt = (
        select(Invocation)
        .where(Invocation.function_id == args["function_id"])
        .order_by(Invocation.created_at.desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    invocations = result.scalars().all()

    if not invocations:
        return {"logs": [], "message": "No invocations yet."}

    return {
        "logs": [
            {
                "status": inv.status,
                "duration_ms": inv.duration_ms,
                "input": inv.input,
                "output": inv.output,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invocations
        ]
    }


async def _tool_update_function(db: AsyncSession, args: dict) -> dict:
    """Update a function's name, description, or code."""
    fn = await db.get(Function, args["function_id"])
    if not fn:
        return {"error": f"Function '{args['function_id']}' not found"}

    if "name" in args and args["name"]:
        fn.name = args["name"]
    if "description" in args and args["description"]:
        fn.description = args["description"]
    if "code" in args and args["code"]:
        fn.code = args["code"]

    await db.commit()
    await db.refresh(fn)
    return {
        "success": True,
        "function_id": fn.id,
        "name": fn.name,
        "message": "Function updated.",
    }


async def _tool_delete_function(db: AsyncSession, args: dict) -> dict:
    """Delete a function and its invocation logs."""
    fn = await db.get(Function, args["function_id"])
    if not fn:
        return {"error": f"Function '{args['function_id']}' not found"}

    name = fn.name
    await db.delete(fn)
    await db.commit()
    return {"success": True, "message": f"Function '{name}' deleted."}
