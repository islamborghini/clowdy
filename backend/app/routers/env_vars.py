"""
Environment variables router.

Manages per-project environment variables that get injected into Docker
containers at function invocation time. Secret values are masked in API
responses but stored in plain text in the database for injection.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import EnvVar
from app.routers.projects import _get_user_project
from app.schemas import EnvVarResponse, EnvVarSet

router = APIRouter(prefix="/api/projects", tags=["env_vars"])

MASKED_VALUE = "********"


@router.get("/{project_id}/env", response_model=list[EnvVarResponse])
async def list_env_vars(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all environment variables for a project. Secret values are masked."""
    await _get_user_project(db, project_id, user_id)

    result = await db.execute(
        select(EnvVar)
        .where(EnvVar.project_id == project_id)
        .order_by(EnvVar.key)
    )
    env_vars = result.scalars().all()

    return [
        EnvVarResponse(
            id=ev.id,
            key=ev.key,
            value=MASKED_VALUE if ev.is_secret else ev.value,
            is_secret=ev.is_secret,
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        )
        for ev in env_vars
    ]


@router.post("/{project_id}/env", response_model=EnvVarResponse)
async def set_env_var(
    project_id: str,
    data: EnvVarSet,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Set an environment variable on a project.

    If the key already exists, its value and is_secret flag are updated
    (upsert behavior). This avoids forcing the client to check existence first.
    """
    await _get_user_project(db, project_id, user_id)

    # Check if this key already exists for the project
    result = await db.execute(
        select(EnvVar).where(
            EnvVar.project_id == project_id,
            EnvVar.key == data.key,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = data.value
        existing.is_secret = data.is_secret
        await db.commit()
        await db.refresh(existing)
        ev = existing
    else:
        ev = EnvVar(
            project_id=project_id,
            key=data.key,
            value=data.value,
            is_secret=data.is_secret,
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)

    return EnvVarResponse(
        id=ev.id,
        key=ev.key,
        value=MASKED_VALUE if ev.is_secret else ev.value,
        is_secret=ev.is_secret,
        created_at=ev.created_at,
        updated_at=ev.updated_at,
    )


@router.delete("/{project_id}/env/{key}")
async def delete_env_var(
    project_id: str,
    key: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an environment variable by key."""
    await _get_user_project(db, project_id, user_id)

    result = await db.execute(
        select(EnvVar).where(
            EnvVar.project_id == project_id,
            EnvVar.key == key,
        )
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail=f"Env var '{key}' not found")

    await db.delete(ev)
    await db.commit()
    return {"detail": f"Env var '{key}' deleted"}
