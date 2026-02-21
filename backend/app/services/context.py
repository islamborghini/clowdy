"""
Execution context resolver.

Shared logic for resolving the environment a function runs in:
env vars, custom Docker image, DATABASE_URL. Used by both the
invoke and gateway routers to avoid duplicating this logic.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EnvVar, Project
from app.services.image_builder import get_image_name


@dataclass
class ExecutionContext:
    """Everything needed to run a function besides the code itself."""
    env_vars: dict[str, str] | None
    image_name: str | None


async def resolve_context(project_id: str | None, db: AsyncSession) -> ExecutionContext:
    """
    Resolve the execution context for a function's project.

    Fetches env vars, custom image name, and DATABASE_URL for injection
    into the Docker container.
    """
    if not project_id:
        return ExecutionContext(env_vars=None, image_name=None)

    env_vars = None
    image_name = None

    # Fetch project env vars
    ev_result = await db.execute(
        select(EnvVar).where(EnvVar.project_id == project_id)
    )
    env_var_rows = ev_result.scalars().all()
    if env_var_rows:
        env_vars = {ev.key: ev.value for ev in env_var_rows}

    # Check for custom image and DATABASE_URL
    project = await db.get(Project, project_id)
    if project:
        if project.requirements_hash:
            image_name = get_image_name(project.id, project.requirements_hash)

        if project.database_url:
            if env_vars is None:
                env_vars = {}
            env_vars["DATABASE_URL"] = project.database_url

    return ExecutionContext(env_vars=env_vars, image_name=image_name)
