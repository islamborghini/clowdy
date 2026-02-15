"""
Runner script that executes user-submitted functions inside a Docker container.

This script is baked into the clowdy-python-runtime Docker image. When a
container starts, it:

1. Reads the user's function code from /app/function.py (mounted volume)
2. Reads the JSON input from the INPUT_JSON environment variable
3. Dynamically imports the user's code and calls handler(input)
4. Prints the return value as JSON to stdout

FastAPI captures stdout to get the function's result. If anything goes wrong
(syntax error, runtime exception, missing handler), the script prints a JSON
error object instead so the backend always gets valid JSON back.
"""

import importlib.util
import inspect
import json
import os
import sys
import traceback


def main():
    # Read the input data from an environment variable.
    # The backend sets INPUT_JSON to the JSON string the caller sent.
    raw_input = os.environ.get("INPUT_JSON", "{}")
    try:
        input_data = json.loads(raw_input)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    # Dynamically import the user's function file.
    # importlib.util lets us load a .py file from a file path at runtime,
    # which is how we run arbitrary user code without knowing the module name
    # ahead of time.
    try:
        spec = importlib.util.spec_from_file_location("user_function", "/app/function.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        print(json.dumps({"error": f"Failed to load function: {traceback.format_exc()}"}))
        sys.exit(1)

    # Check that the user defined a handler() function.
    if not hasattr(module, "handler"):
        print(json.dumps({"error": "Function must define a handler(input) function"}))
        sys.exit(1)

    # Detect handler signature: handler(input) vs handler(event, context).
    # The gateway passes a rich event dict with method/path/params/query/headers/body.
    # Functions using handler(event, context) get a context dict with metadata.
    # Old-style handler(input) still works exactly as before.
    try:
        sig = inspect.signature(module.handler)
        param_count = len(sig.parameters)
    except (ValueError, TypeError):
        param_count = 1

    try:
        if param_count >= 2:
            context = {
                "function_name": os.environ.get("FUNCTION_NAME", "unknown"),
                "runtime": "python",
            }
            result = module.handler(input_data, context)
        else:
            result = module.handler(input_data)
    except Exception:
        print(json.dumps({"error": f"Function error: {traceback.format_exc()}"}))
        sys.exit(1)

    # Print the result as JSON so the backend can capture it from stdout.
    try:
        print(json.dumps(result))
    except (TypeError, ValueError):
        print(json.dumps({"error": f"Function returned non-JSON-serializable value: {type(result).__name__}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
