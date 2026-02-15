"""
AI Agent service powered by Groq.

This module connects to Groq's API (free, fast LLM inference) and gives the
AI model a set of "tools" - functions it can call to interact with the Clowdy
platform. When a user sends a chat message like "create a function that adds
two numbers", the AI:

1. Understands the intent from the natural language
2. Outputs a structured "tool call" (e.g. create_function with name + code)
3. We execute that tool call against the real database
4. Feed the result back to the AI
5. The AI writes a human-friendly response

This is the same pattern used by ChatGPT plugins, Claude's tool use, and
GitHub Copilot - the AI translates English into API calls.

Key concepts:
- Tool definitions: JSON schemas that tell the AI what functions exist and
  what parameters they accept (like an API spec for the AI)
- Tool calls: The AI's structured output saying "call this function with
  these arguments"
- Tool results: What we send back to the AI after executing the tool call
"""

import json

from groq import Groq

from app.config import GROQ_API_KEY


# The model to use. Llama 4 Scout supports tool calling reliably on Groq.
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# System prompt that tells the AI who it is and how to behave.
SYSTEM_PROMPT = """You are Clowdy, an AI assistant for a serverless function platform.
You help users create, manage, and test Python functions.

When a user asks you to create a function, write clean Python code with a
handler(input) function. The handler receives a dict and should return a dict.

Example function:
def handler(input):
    name = input.get("name", "World")
    return {"message": f"Hello, {name}!"}

Keep responses concise and helpful. When you create or modify a function,
briefly explain what it does. When showing function details, format them clearly."""

# Tool definitions - these tell the AI what actions it can take.
# Each tool has a name, description, and parameter schema (JSON Schema format).
# The AI reads these to decide which tool to call and with what arguments.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_function",
            "description": "Create and deploy a new serverless function. The code must define a handler(input) function that takes a dict and returns a dict.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short name for the function (e.g. 'greeter', 'calculator')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the function does",
                    },
                    "code": {
                        "type": "string",
                        "description": "Python source code. Must define a handler(input) function.",
                    },
                },
                "required": ["name", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_functions",
            "description": "List all deployed functions with their names, IDs, and status.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_function",
            "description": "Run/test a deployed function with the given input data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_id": {
                        "type": "string",
                        "description": "The ID of the function to invoke",
                    },
                    "input": {
                        "type": "object",
                        "description": "JSON input data to pass to the function's handler",
                    },
                },
                "required": ["function_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_logs",
            "description": "View recent invocation logs for a function (shows input, output, status, duration).",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_id": {
                        "type": "string",
                        "description": "The ID of the function to view logs for",
                    },
                },
                "required": ["function_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_function",
            "description": "Update a function's code, name, or description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_id": {
                        "type": "string",
                        "description": "The ID of the function to update",
                    },
                    "name": {
                        "type": "string",
                        "description": "New name for the function (optional)",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description (optional)",
                    },
                    "code": {
                        "type": "string",
                        "description": "New Python code (optional, must define handler(input))",
                    },
                },
                "required": ["function_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_function",
            "description": "Delete a deployed function and all its invocation logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_id": {
                        "type": "string",
                        "description": "The ID of the function to delete",
                    },
                },
                "required": ["function_id"],
            },
        },
    },
]


def get_groq_client() -> Groq:
    """Create a Groq client. Raises an error if the API key is not set."""
    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
            "and set it: export GROQ_API_KEY='gsk_...'"
        )
    return Groq(api_key=GROQ_API_KEY)


async def chat_with_tools(
    messages: list[dict],
    execute_tool: callable,
) -> dict:
    """
    Send a conversation to Groq and handle any tool calls the AI makes.

    This is the core loop of the AI agent:
    1. Send the conversation (with tool definitions) to Groq
    2. If Groq responds with tool calls, execute each one
    3. Feed the tool results back to Groq
    4. Groq writes a final human-readable response

    Args:
        messages: The conversation history (list of {role, content} dicts).
                  The system prompt is prepended automatically.
        execute_tool: An async function that takes (tool_name, tool_args) and
                      returns a result string. This is how we connect the AI's
                      tool calls to the real database operations.

    Returns:
        A dict with:
            response (str): The AI's final text response
            tool_calls (list): Any tool calls that were made, with their results
    """
    client = get_groq_client()

    # Prepend the system prompt to the conversation
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # Step 1: Send to Groq with tool definitions
    completion = client.chat.completions.create(
        model=MODEL,
        messages=full_messages,
        tools=TOOLS,
        tool_choice="auto",  # Let the AI decide whether to use tools
    )

    response_message = completion.choices[0].message
    tool_calls_made = []

    # Step 2: If the AI wants to call tools, execute them
    if response_message.tool_calls:
        # Add the AI's response (with tool calls) to the conversation
        full_messages.append(response_message)

        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # Execute the tool and get the result
            result = await execute_tool(tool_name, tool_args)

            tool_calls_made.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            })

            # Add the tool result to the conversation so the AI can see it
            full_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result) if isinstance(result, dict) else str(result),
            })

        # Step 3: Send the conversation (with tool results) back to Groq
        # so it can write a human-friendly response
        second_completion = client.chat.completions.create(
            model=MODEL,
            messages=full_messages,
        )
        final_response = second_completion.choices[0].message.content
    else:
        # No tool calls - the AI just responded with text
        final_response = response_message.content

    return {
        "response": final_response,
        "tool_calls": tool_calls_made,
    }
