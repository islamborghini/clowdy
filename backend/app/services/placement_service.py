"""
Placement Service -- creates and destroys execution environments (containers).

AWS Lambda equivalent: Placement Service.
Only called on cold starts when the Assignment Service has no warm container.

This service owns the Docker client and is the only place where containers
are created or destroyed.
"""

import os

import docker


# Default runtime image. Must be built before first use:
# cd backend/docker/runtimes/python && docker build -t clowdy-python-runtime .
DEFAULT_IMAGE = "clowdy-python-runtime"

# Resource limits for function containers
MEMORY_LIMIT = "128m"
NANO_CPUS = 500_000_000  # 0.5 CPU cores


def _get_docker_client() -> docker.DockerClient:
    """
    Create a Docker client, handling non-standard socket locations.

    On macOS with Colima, the Docker socket is not at the default
    /var/run/docker.sock. We check DOCKER_HOST env var first, then
    try the Colima socket path, then fall back to the default.
    """
    if os.environ.get("DOCKER_HOST"):
        return docker.from_env()

    home = os.path.expanduser("~")
    colima_sock = os.path.join(home, ".colima", "default", "docker.sock")
    if os.path.exists(colima_sock):
        return docker.DockerClient(base_url=f"unix://{colima_sock}")

    return docker.from_env()


class PlacementService:
    """
    Creates new execution environments (Docker containers).

    Containers are created with `sleep infinity` as the command so they
    stay alive between invocations. Code execution happens via `docker exec`
    in the worker service.
    """

    def __init__(self):
        self.client = _get_docker_client()

    def create(self, image: str, network_enabled: bool = False):
        """
        Create and start a new container that stays alive.

        Args:
            image: Docker image name (e.g. "clowdy-python-runtime" or custom)
            network_enabled: Whether to allow outbound network access

        Returns:
            A running Docker container ready to accept exec calls.
        """
        container = self.client.containers.create(
            image,
            command=["sleep", "infinity"],
            network_disabled=not network_enabled,
            mem_limit=MEMORY_LIMIT,
            nano_cpus=NANO_CPUS,
        )
        container.start()
        return container

    def destroy(self, container):
        """Remove a container permanently."""
        try:
            container.remove(force=True)
        except Exception:
            pass
