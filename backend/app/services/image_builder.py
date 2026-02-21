"""
Custom Docker image builder for project dependencies.

When a project has pip dependencies (requirements.txt), we build a custom
Docker image that extends the base clowdy-python-runtime with those packages
installed. This image is then used for all function invocations in that project.

The build flow:
1. Compute a hash of the requirements (for cache invalidation)
2. Generate a Dockerfile that extends the base image and pip installs the deps
3. Build the image using the Docker SDK
4. Tag it as clowdy-project-{project_id}:{hash[:8]}

Images are cached by hash -- if requirements haven't changed, we skip the build.
"""

import hashlib
import io
import tarfile

import docker
from docker.errors import BuildError, ImageNotFound

from app.services.placement_service import _get_docker_client

# Base image that all custom images extend
BASE_IMAGE = "clowdy-python-runtime"


def compute_requirements_hash(requirements_txt: str) -> str:
    """
    Compute a stable SHA256 hash of the requirements.

    We sort and strip lines so that reordering or adding whitespace
    doesn't trigger an unnecessary rebuild.
    """
    lines = sorted(
        line.strip()
        for line in requirements_txt.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    content = "\n".join(lines)
    return hashlib.sha256(content.encode()).hexdigest()


def get_image_name(project_id: str, requirements_hash: str) -> str:
    """Return the Docker image name for a project with the given hash."""
    return f"clowdy-project-{project_id}:{requirements_hash[:8]}"


def image_exists(image_name: str) -> bool:
    """Check if a Docker image with the given name exists locally."""
    client = _get_docker_client()
    try:
        client.images.get(image_name)
        return True
    except ImageNotFound:
        return False


def build_project_image(
    project_id: str, requirements_txt: str
) -> tuple[bool, str, str]:
    """
    Build a custom Docker image with the project's pip dependencies.

    Args:
        project_id: The project ID (used in the image tag)
        requirements_txt: The full requirements.txt content

    Returns:
        A tuple of (success, image_name_or_error, requirements_hash)
        - On success: (True, "clowdy-project-abc123:a1b2c3d4", "full_hash")
        - On failure: (False, "error message", "")
    """
    req_hash = compute_requirements_hash(requirements_txt)
    image_name = get_image_name(project_id, req_hash)

    # Check if image already exists (cached)
    if image_exists(image_name):
        return True, image_name, req_hash

    # Build the image from an in-memory context
    dockerfile_content = (
        f"FROM {BASE_IMAGE}\n"
        "COPY requirements.txt /tmp/requirements.txt\n"
        "RUN pip install --no-cache-dir -r /tmp/requirements.txt "
        "&& rm /tmp/requirements.txt\n"
    )

    # Create an in-memory tar archive with the Dockerfile and requirements.txt
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode="w") as tar:
        # Add Dockerfile
        df_data = dockerfile_content.encode("utf-8")
        df_info = tarfile.TarInfo(name="Dockerfile")
        df_info.size = len(df_data)
        tar.addfile(df_info, io.BytesIO(df_data))

        # Add requirements.txt
        req_data = requirements_txt.encode("utf-8")
        req_info = tarfile.TarInfo(name="requirements.txt")
        req_info.size = len(req_data)
        tar.addfile(req_info, io.BytesIO(req_data))

    context.seek(0)

    client = _get_docker_client()
    try:
        client.images.build(
            fileobj=context,
            custom_context=True,
            tag=image_name,
            rm=True,
            forcerm=True,
        )
        # Clean up old images for this project
        cleanup_old_images(project_id, req_hash)
        return True, image_name, req_hash

    except BuildError as exc:
        # Extract the actual build log so the user sees pip's error output
        log_lines = []
        for chunk in exc.build_log:
            if isinstance(chunk, dict):
                stream = chunk.get("stream", "").strip()
                error = chunk.get("error", "").strip()
                if error:
                    log_lines.append(error)
                elif stream:
                    log_lines.append(stream)
            elif isinstance(chunk, str):
                log_lines.append(chunk.strip())
        # Show the last few lines which usually contain the actual error
        relevant = [l for l in log_lines if l][-10:]
        error_msg = "\n".join(relevant) if relevant else str(exc)
        return False, error_msg, ""

    except Exception as exc:
        return False, str(exc), ""


def cleanup_old_images(project_id: str, keep_hash: str) -> None:
    """
    Remove old Docker images for a project, keeping only the current one.

    Images are tagged as clowdy-project-{project_id}:{hash[:8]}, so we
    find all images matching the project prefix and remove any that don't
    match the current hash.
    """
    client = _get_docker_client()
    keep_tag = f"clowdy-project-{project_id}:{keep_hash[:8]}"
    prefix = f"clowdy-project-{project_id}:"

    try:
        images = client.images.list()
        for image in images:
            for tag in (image.tags or []):
                if tag.startswith(prefix) and tag != keep_tag:
                    try:
                        client.images.remove(tag, force=True)
                    except Exception:
                        pass
    except Exception:
        # Cleanup is best-effort, don't fail the build
        pass
