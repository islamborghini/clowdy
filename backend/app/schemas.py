from datetime import datetime

from pydantic import BaseModel


# --- Function schemas ---


class FunctionCreate(BaseModel):
    name: str
    description: str = ""
    code: str
    runtime: str = "python"


class FunctionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code: str | None = None


class FunctionResponse(BaseModel):
    id: str
    name: str
    description: str
    code: str
    runtime: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Invocation schemas ---


class InvokeRequest(BaseModel):
    input: dict = {}


class InvocationResponse(BaseModel):
    id: str
    function_id: str
    input: str
    output: str
    status: str
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}
