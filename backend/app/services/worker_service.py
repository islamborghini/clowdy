"""
Worker Service -- executes user code inside a container.

AWS Lambda equivalent: the Worker (Firecracker microVM execution).

This service does NOT create or destroy containers. It receives an
already-running container, copies the user's code in, runs it via
`docker exec`, and returns the result.
"""

import io
import json
import tarfile


TIMEOUT_SECONDS = 30


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


def execute(
    container,
    code: str,
    input_data: dict,
    env_vars: dict[str, str] | None = None,
    function_name: str = "unknown",
) -> dict:
    """
    Run user code inside an existing container via docker exec.

    Steps:
    1. Copy function.py into the container at /app/
    2. Build environment variables for the exec call
    3. Run `python /app/runner.py` inside the container
    4. Parse stdout as the function's return value

    Args:
        container: A running Docker container
        code: The user's Python source code (must define a handler function)
        input_data: Dictionary of input data to pass to handler()
        env_vars: Optional env vars to inject (project env vars, DATABASE_URL)
        function_name: Name of the function for the context object

    Returns:
        dict with keys: success (bool), output (any)
    """
    # 1. Copy the user's code into the container
    tar_data = _make_tar("function.py", code)
    container.put_archive("/app", tar_data)

    # 2. Build environment for the exec call
    exec_env = {}
    if env_vars:
        exec_env.update(env_vars)
    exec_env["INPUT_JSON"] = json.dumps(input_data)
    exec_env["FUNCTION_NAME"] = function_name

    # 3. Execute runner.py inside the container
    exit_code, output = container.exec_run(
        ["python", "/app/runner.py"],
        environment=exec_env,
    )

    # 4. Parse the output
    stdout = output.decode("utf-8").strip()

    if exit_code != 0:
        error_msg = stdout or "Function exited with an error"
        try:
            error_data = json.loads(error_msg)
            error_msg = error_data.get("error", error_msg)
        except json.JSONDecodeError:
            pass
        return {"success": False, "output": error_msg}

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = stdout

    return {"success": True, "output": parsed}
