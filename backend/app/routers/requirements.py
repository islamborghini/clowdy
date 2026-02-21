"""
Project requirements (pip dependencies) router.

Handles viewing and updating a project's pip dependencies. When
requirements are updated, a custom Docker image is built with
those packages installed. The image is then used for all function
invocations in that project.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Project
from app.schemas import RequirementsResponse, RequirementsUpdate
from app.services.image_builder import (
    build_project_image,
    compute_requirements_hash,
    get_image_name,
    image_exists,
)

router = APIRouter(prefix="/api/projects", tags=["requirements"])


async def _get_user_project(
    db: AsyncSession, project_id: str, user_id: str
) -> Project:
    """Fetch a project, raising 404 if not found or not owned by user."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get(
    "/{project_id}/requirements", response_model=RequirementsResponse
)
async def get_requirements(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current pip dependencies for a project."""
    project = await _get_user_project(db, project_id, user_id)

    has_image = False
    if project.requirements_hash:
        image_name = get_image_name(project.id, project.requirements_hash)
        has_image = await asyncio.to_thread(image_exists, image_name)

    return RequirementsResponse(
        requirements_txt=project.requirements_txt,
        requirements_hash=project.requirements_hash,
        has_custom_image=has_image,
    )


@router.put(
    "/{project_id}/requirements", response_model=RequirementsResponse
)
async def update_requirements(
    project_id: str,
    data: RequirementsUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a project's pip dependencies and build a custom Docker image.

    If requirements are empty, clears the custom image and reverts to
    the default runtime. If requirements haven't changed (same hash),
    skips the build.
    """
    project = await _get_user_project(db, project_id, user_id)
    requirements_txt = data.requirements_txt.strip()

    # Empty requirements -> clear and revert to default image
    if not requirements_txt:
        project.requirements_txt = ""
        project.requirements_hash = ""
        await db.commit()
        await db.refresh(project)
        return RequirementsResponse(
            requirements_txt="",
            requirements_hash="",
            has_custom_image=False,
        )

    # Check if requirements have changed
    new_hash = compute_requirements_hash(requirements_txt)
    if new_hash == project.requirements_hash:
        image_name = get_image_name(project.id, new_hash)
        has_image = await asyncio.to_thread(image_exists, image_name)
        if has_image:
            return RequirementsResponse(
                requirements_txt=project.requirements_txt,
                requirements_hash=project.requirements_hash,
                has_custom_image=True,
            )
        # Image is missing (e.g. Docker prune), fall through to rebuild

    # Build the custom image (synchronous, runs in thread pool)
    success, result, req_hash = await asyncio.to_thread(
        build_project_image, project.id, requirements_txt
    )

    if not success:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to build image: {result}",
        )

    # Update the project with the new requirements
    project.requirements_txt = requirements_txt
    project.requirements_hash = req_hash
    await db.commit()
    await db.refresh(project)

    return RequirementsResponse(
        requirements_txt=project.requirements_txt,
        requirements_hash=project.requirements_hash,
        has_custom_image=True,
    )
