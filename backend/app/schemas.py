"""
Pydantic schemas for request/response validation.

Pydantic models serve a different purpose than SQLAlchemy models:
- SQLAlchemy models = database table structure (how data is STORED)
- Pydantic schemas = API request/response structure (how data is SENT/RECEIVED)

FastAPI uses Pydantic to:
1. Validate incoming request data (reject bad requests automatically)
2. Serialize response data to JSON
3. Generate OpenAPI documentation (visible at /docs)

Why separate from SQLAlchemy models? Because what you store in the DB
is often different from what you expose in the API. For example, you
might store a hashed password in the DB but never include it in API responses.
"""

from datetime import datetime

from pydantic import BaseModel


# --- Project schemas ---


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    """Schema for updating a project. All fields optional."""

    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    """Schema for project data returned by the API."""

    id: str
    name: str
    slug: str
    description: str
    status: str
    function_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Function schemas ---


class FunctionCreate(BaseModel):
    """
    Schema for creating a new function (POST /api/functions).

    The client sends this JSON in the request body. FastAPI automatically
    validates that "name" and "code" are present and are strings.
    "description" and "runtime" have defaults, so they're optional.
    """

    name: str
    description: str = ""
    code: str
    runtime: str = "python"
    project_id: str | None = None


class FunctionUpdate(BaseModel):
    """
    Schema for updating an existing function (PUT /api/functions/:id).

    All fields are optional (str | None) - the client only sends the
    fields they want to change. For example, to rename a function:
        { "name": "new_name" }
    """

    name: str | None = None
    description: str | None = None
    code: str | None = None


class FunctionResponse(BaseModel):
    """
    Schema for function data returned by the API.

    model_config = {"from_attributes": True} tells Pydantic to read data
    from SQLAlchemy model attributes (e.g., fn.name) instead of expecting
    a dictionary. This lets us return SQLAlchemy objects directly from routes.
    """

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
    """
    Schema for invoking a function (POST /api/invoke/:id).

    The client sends input data as a JSON object. Defaults to empty dict
    so functions can be called with no input.
    """

    input: dict = {}


class InvocationResponse(BaseModel):
    """Schema for invocation log data returned by the API."""

    id: str
    function_id: str
    input: str
    output: str
    status: str
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}
