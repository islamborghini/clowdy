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
import io
import json
import os
import tarfile
import time

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
    home = os.path.expanduser("~")
    colima_sock = os.path.join(home, ".colima", "default", "docker.sock")
    if os.path.exists(colima_sock):
        return docker.DockerClient(base_url=f"unix://{colima_sock}")

    # Fall back to default
    return docker.from_env()


async def run_function(
    code: str,
    input_data: dict,
    env_vars: dict[str, str] | None = None,
    function_name: str = "unknown",
) -> dict:
    """
    Execute a user's function code inside a Docker container.

    This is an async function because FastAPI is async, but the Docker SDK
    is synchronous. We use asyncio.to_thread() to run the blocking Docker
    calls in a thread pool so they don't block the event loop.

    Args:
        code: The user's Python source code (must define a handler function)
        input_data: Dictionary of input data to pass to handler()
        env_vars: Optional dict of environment variables to inject into the
                  container. These come from the project's env var settings
                  and are accessible via os.environ inside the function.
        function_name: Name of the function, passed to the container as
                       FUNCTION_NAME env var for use in handler(event, context).

    Returns:
        A dict with keys:
            success (bool): Whether the function ran without errors
            output (dict | str): The function's return value, or error message
            duration_ms (int): How long execution took in milliseconds
    """
    # Run the blocking Docker operations in a separate thread.
    # This prevents the async event loop from freezing while Docker works.
    return await asyncio.to_thread(
        _run_in_container, code, input_data, env_vars, function_name
    )


def _make_tar(filename: str, content: str) -> bytes:
    """
    Create an in-memory tar archive containing a single file.

    Docker's put_archive API requires a tar stream to copy files into a
    container. This builds that tar archive in memory so we don't need
    to write anything to the host filesystem.
    """
    data = content.encode("utf-8")
    tarstream = io.BytesIO()
    with tarfile.open(fileobj=tarstream, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    tarstream.seek(0)
    return tarstream.read()


def _run_in_container(
    code: str,
    input_data: dict,
    env_vars: dict[str, str] | None = None,
    function_name: str = "unknown",
) -> dict:
    """
    Synchronous function that does the actual Docker work.

    Steps:
    1. Create a container (stopped) from the runtime image
    2. Copy user code into the container using put_archive (docker cp)
    3. Start the container and wait for it to finish (or timeout)
    4. Read stdout for the result
    5. Clean up the container
    6. Return the result with timing info

    We use put_archive instead of volume mounts because volume mounts
    don't work reliably with Colima/remote Docker (the host file path
    isn't accessible inside the VM).
    """
    client = _get_docker_client()
    start_time = time.time()

    container = None
    try:
        # Build the environment dict: start with project env vars (if any),
        # then add INPUT_JSON. Project env vars come first so they can't
        # override INPUT_JSON (which is used by the runner).
        container_env = {}
        if env_vars:
            container_env.update(env_vars)
        container_env["INPUT_JSON"] = json.dumps(input_data)
        container_env["FUNCTION_NAME"] = function_name

        # Create the container in stopped state.
        # We need it stopped first so we can copy the code file in
        # before it starts running.
        # network_disabled: prevent the function from making network calls
        # mem_limit: cap memory at 128MB to prevent abuse
        # nano_cpus: limit to 0.5 CPU cores (500 million nanocpus)
        container = client.containers.create(
            IMAGE_NAME,
            environment=container_env,
            network_disabled=True,
            mem_limit="128m",
            nano_cpus=500_000_000,
        )

        # Copy the user's code into the container at /app/function.py.
        # put_archive takes a tar archive and extracts it at the given path.
        tar_data = _make_tar("function.py", code)
        container.put_archive("/app", tar_data)

        # Start the container and wait for it to finish.
        container.start()
        result = container.wait(timeout=TIMEOUT_SECONDS)
        exit_code = result.get("StatusCode", -1)

        # Read stdout (the function's result) and stderr (any errors).
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
        # Always clean up: remove the container.
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass
