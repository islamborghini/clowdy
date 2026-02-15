"""
Docker-based function execution service.

This module handles the actual running of user code inside Docker containers.
It uses the Docker SDK for Python (not shell commands) to:

1. Create a container from the clowdy-python-runtime image
2. Mount the user's code file into the container
3. Pass input data as an environment variable
4. Run the container with a timeout
5. Capture the output (stdout) and return it
6. Clean up the container after execution

The key idea: user code is UNTRUSTED. Docker isolates it so it can't access
the host filesystem, network, or other containers. If the code runs too long
(infinite loop), the container is killed after the timeout.

Usage:
    result = await run_function(code="def handler(input): ...", input_data={"name": "World"})
    # result is a dict like:
    # {"success": True, "output": {"message": "Hello, World!"}, "duration_ms": 123}
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import docker
from docker.errors import ContainerError, ImageNotFound, APIError


# Name of the Docker image we built from the Dockerfile.
# Must be built before first use: docker build -t clowdy-python-runtime .
IMAGE_NAME = "clowdy-python-runtime"

# Maximum time (seconds) a function is allowed to run before being killed.
TIMEOUT_SECONDS = 30


def _get_docker_client() -> docker.DockerClient:
    """
    Create a Docker client, handling non-standard socket locations.

    On macOS with Colima, the Docker socket is not at the default
    /var/run/docker.sock. We check DOCKER_HOST env var first, then
    try the Colima socket path, then fall back to the default.
    """
    # If DOCKER_HOST is set, the SDK will use it automatically
    if os.environ.get("DOCKER_HOST"):
        return docker.from_env()

    # Check for Colima socket (common on macOS)
    colima_sock = Path.home() / ".colima" / "default" / "docker.sock"
    if colima_sock.exists():
        return docker.DockerClient(base_url=f"unix://{colima_sock}")

    # Fall back to default
    return docker.from_env()


async def run_function(code: str, input_data: dict) -> dict:
    """
    Execute a user's function code inside a Docker container.

    This is an async function because FastAPI is async, but the Docker SDK
    is synchronous. We use asyncio.to_thread() to run the blocking Docker
    calls in a thread pool so they don't block the event loop.

    Args:
        code: The user's Python source code (must define a handler function)
        input_data: Dictionary of input data to pass to handler()

    Returns:
        A dict with keys:
            success (bool): Whether the function ran without errors
            output (dict | str): The function's return value, or error message
            duration_ms (int): How long execution took in milliseconds
    """
    # Run the blocking Docker operations in a separate thread.
    # This prevents the async event loop from freezing while Docker works.
    return await asyncio.to_thread(_run_in_container, code, input_data)


def _run_in_container(code: str, input_data: dict) -> dict:
    """
    Synchronous function that does the actual Docker work.

    Steps:
    1. Write user code to a temporary file on disk
    2. Create and start a Docker container
    3. Mount the temp file into the container
    4. Wait for the container to finish (or timeout)
    5. Read stdout for the result
    6. Clean up the container
    7. Return the result with timing info
    """
    client = _get_docker_client()
    start_time = time.time()

    # Write the user's code to a temporary file.
    # tempfile.NamedTemporaryFile creates a file that's automatically
    # deleted when closed, but we keep it open until the container is done.
    # suffix=".py" ensures the file ends in .py for the Python import to work.
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    tmp.write(code)
    tmp.flush()
    tmp_path = tmp.name
    tmp.close()

    container = None
    try:
        # Create and start the container.
        # volumes: mount the temp file as /app/function.py inside the container
        # environment: pass the input data as a JSON string
        # network_disabled: prevent the function from making network calls
        # mem_limit: cap memory at 128MB to prevent abuse
        # nano_cpus: limit to 0.5 CPU cores (500 million nanocpus)
        container = client.containers.run(
            IMAGE_NAME,
            detach=True,
            volumes={tmp_path: {"bind": "/app/function.py", "mode": "ro"}},
            environment={"INPUT_JSON": json.dumps(input_data)},
            network_disabled=True,
            mem_limit="128m",
            nano_cpus=500_000_000,
        )

        # Wait for the container to finish, with a timeout.
        # container.wait() blocks until the container exits or timeout is reached.
        result = container.wait(timeout=TIMEOUT_SECONDS)
        exit_code = result.get("StatusCode", -1)

        # Read stdout (the function's result) and stderr (any print statements or errors).
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8").strip()
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8").strip()

        duration_ms = int((time.time() - start_time) * 1000)

        if exit_code != 0:
            # The function crashed or returned an error.
            # Try to parse stdout as JSON (runner.py prints JSON errors),
            # fall back to stderr or a generic message.
            error_msg = stdout or stderr or "Function exited with an error"
            try:
                error_data = json.loads(error_msg)
                error_msg = error_data.get("error", error_msg)
            except json.JSONDecodeError:
                pass
            return {"success": False, "output": error_msg, "duration_ms": duration_ms}

        # Parse the JSON output from stdout.
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            output = stdout

        return {"success": True, "output": output, "duration_ms": duration_ms}

    except ConnectionError:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "output": "Could not connect to Docker. Is Docker running?",
            "duration_ms": duration_ms,
        }

    except ImageNotFound:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "output": (
                f"Docker image '{IMAGE_NAME}' not found. "
                "Build it with: cd backend/docker/runtimes/python && "
                "docker build -t clowdy-python-runtime ."
            ),
            "duration_ms": duration_ms,
        }

    except (ContainerError, APIError) as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        # Check if this is a timeout (container killed after TIMEOUT_SECONDS)
        error_str = str(exc).lower()
        if "timeout" in error_str or "deadline" in error_str:
            return {
                "success": False,
                "output": f"Function timed out after {TIMEOUT_SECONDS} seconds",
                "duration_ms": duration_ms,
            }
        return {"success": False, "output": str(exc), "duration_ms": duration_ms}

    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        return {"success": False, "output": f"Unexpected error: {exc}", "duration_ms": duration_ms}

    finally:
        # Always clean up: remove the container and the temp file.
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
