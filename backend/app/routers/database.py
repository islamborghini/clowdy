"""
Database provisioning router.

Manages per-project Neon PostgreSQL databases. Users can provision
a managed Postgres database for their project, which automatically
injects DATABASE_URL into function containers at runtime.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import NEON_API_KEY
from app.database import get_db
from app.models import Project
from app.schemas import DatabaseResponse
from app.services.neon_service import (
    deprovision_database,
    mask_connection_string,
    provision_database,
)

router = APIRouter(prefix="/api/projects/{project_id}/database", tags=["database"])


async def _get_user_project(
    db: AsyncSession, project_id: str, user_id: str
) -> Project:
    """Fetch a project, raising 404 if not found or not owned by user."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=DatabaseResponse)
async def get_database_status(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current database status for a project."""
    project = await _get_user_project(db, project_id, user_id)
    return DatabaseResponse(
        has_database=bool(project.neon_project_id),
        database_url=mask_connection_string(project.database_url),
        neon_project_id=project.neon_project_id,
    )


@router.post("/provision", response_model=DatabaseResponse)
async def provision_project_database(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Provision a new Neon PostgreSQL database for this project."""
    project = await _get_user_project(db, project_id, user_id)

    if project.neon_project_id:
        raise HTTPException(
            status_code=409, detail="Project already has a database"
        )

    if not NEON_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Neon API key not configured. Set NEON_API_KEY in .env.local",
        )

    try:
        neon_project_id, connection_uri = await provision_database(project.slug)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to provision database: {exc}",
        )

    project.neon_project_id = neon_project_id
    project.database_url = connection_uri
    await db.commit()
    await db.refresh(project)

    return DatabaseResponse(
        has_database=True,
        database_url=mask_connection_string(project.database_url),
        neon_project_id=project.neon_project_id,
    )


@router.delete("/deprovision", response_model=DatabaseResponse)
async def deprovision_project_database(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the Neon PostgreSQL database for this project."""
    project = await _get_user_project(db, project_id, user_id)

    if not project.neon_project_id:
        raise HTTPException(
            status_code=400, detail="Project does not have a database"
        )

    try:
        await deprovision_database(project.neon_project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to deprovision database: {exc}",
        )

    project.neon_project_id = ""
    project.database_url = ""
    await db.commit()
    await db.refresh(project)

    return DatabaseResponse(
        has_database=False,
        database_url="",
        neon_project_id="",
    )
