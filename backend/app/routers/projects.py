"""
Projects CRUD router.

Handles creating, reading, updating, and deleting projects.
Projects group related functions under a single deployable unit.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Function, Project
from app.schemas import (
    FunctionResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _slugify(name: str) -> str:
    """Convert a project name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Ensure the slug is unique by appending a number if needed."""
    slug = base_slug
    counter = 1
    while True:
        exists = await db.execute(select(Project).where(Project.slug == slug).limit(1))
        if not exists.scalar_one_or_none():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


async def _get_user_project(
    db: AsyncSession, project_id: str, user_id: str
) -> Project:
    """Fetch a project, raising 404 if not found or not owned by user."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project with an auto-generated slug."""
    slug = await _unique_slug(db, _slugify(data.name))
    project = Project(
        name=data.name,
        slug=slug,
        description=data.description,
        user_id=user_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        status=project.status,
        function_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects for the authenticated user with function counts."""
    result = await db.execute(
        select(Project, func.count(Function.id).label("fn_count"))
        .outerjoin(Function, Function.project_id == Project.id)
        .where(Project.user_id == user_id)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
    )
    rows = result.all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            slug=p.slug,
            description=p.description,
            status=p.status,
            function_count=fn_count,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p, fn_count in rows
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single project by ID."""
    project = await _get_user_project(db, project_id, user_id)
    fn_count_result = await db.execute(
        select(func.count()).select_from(Function).where(
            Function.project_id == project.id
        )
    )
    fn_count = fn_count_result.scalar() or 0
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        status=project.status,
        function_count=fn_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a project. Only provided fields are changed."""
    project = await _get_user_project(db, project_id, user_id)
    updates = data.model_dump(exclude_unset=True)

    if "name" in updates:
        project.name = updates["name"]
        project.slug = await _unique_slug(db, _slugify(updates["name"]))
    if "description" in updates:
        project.description = updates["description"]

    await db.commit()
    await db.refresh(project)
    fn_count_result = await db.execute(
        select(func.count()).select_from(Function).where(
            Function.project_id == project.id
        )
    )
    fn_count = fn_count_result.scalar() or 0
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        status=project.status,
        function_count=fn_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and all its functions (cascade)."""
    project = await _get_user_project(db, project_id, user_id)
    await db.delete(project)
    await db.commit()
    return {"detail": "Project deleted"}


@router.get("/{project_id}/functions", response_model=list[FunctionResponse])
async def list_project_functions(
    project_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all functions belonging to a project."""
    await _get_user_project(db, project_id, user_id)
    result = await db.execute(
        select(Function)
        .where(Function.project_id == project_id)
        .order_by(Function.created_at.desc())
    )
    return result.scalars().all()
