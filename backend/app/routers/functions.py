from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Function
from app.schemas import FunctionCreate, FunctionResponse, FunctionUpdate

router = APIRouter(prefix="/api/functions", tags=["functions"])


@router.post("", response_model=FunctionResponse)
async def create_function(data: FunctionCreate, db: AsyncSession = Depends(get_db)):
    fn = Function(
        name=data.name,
        description=data.description,
        code=data.code,
        runtime=data.runtime,
    )
    db.add(fn)
    await db.commit()
    await db.refresh(fn)
    return fn


@router.get("", response_model=list[FunctionResponse])
async def list_functions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Function).order_by(Function.created_at.desc()))
    return result.scalars().all()


@router.get("/{function_id}", response_model=FunctionResponse)
async def get_function(function_id: str, db: AsyncSession = Depends(get_db)):
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")
    return fn


@router.put("/{function_id}", response_model=FunctionResponse)
async def update_function(
    function_id: str, data: FunctionUpdate, db: AsyncSession = Depends(get_db)
):
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(fn, field, value)

    await db.commit()
    await db.refresh(fn)
    return fn


@router.delete("/{function_id}")
async def delete_function(function_id: str, db: AsyncSession = Depends(get_db)):
    fn = await db.get(Function, function_id)
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")
    await db.delete(fn)
    await db.commit()
    return {"detail": "Function deleted"}
