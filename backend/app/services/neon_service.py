"""
Neon PostgreSQL service.

Manages per-project Neon databases via the Neon REST API v2.
Each Clowdy project can optionally have a managed Postgres database.
When provisioned, the connection string is automatically injected as
DATABASE_URL into function containers at runtime.

API docs: https://api-docs.neon.tech/reference/getting-started-with-neon-api
"""

from urllib.parse import urlparse, urlunparse

import httpx

from app.config import NEON_API_KEY

NEON_API_BASE = "https://console.neon.tech/api/v2"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {NEON_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def provision_database(project_name: str) -> tuple[str, str]:
    """
    Create a Neon project and return (neon_project_id, connection_uri).

    Creates a project named 'clowdy-{project_name}' with the default
    database (neondb) and role (neondb_owner).
    """
    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Create the Neon project
        create_resp = await client.post(
            f"{NEON_API_BASE}/projects",
            headers=_headers(),
            json={"project": {"name": f"clowdy-{project_name}"}},
        )
        create_resp.raise_for_status()
        project_data = create_resp.json()
        neon_project_id = project_data["project"]["id"]

        # Step 2: Get the connection URI
        uri_resp = await client.get(
            f"{NEON_API_BASE}/projects/{neon_project_id}/connection_uri",
            headers=_headers(),
            params={
                "database_name": "neondb",
                "role_name": "neondb_owner",
            },
        )
        uri_resp.raise_for_status()
        connection_uri = uri_resp.json()["uri"]

        return neon_project_id, connection_uri


async def deprovision_database(neon_project_id: str) -> bool:
    """
    Delete a Neon project. Returns True on success.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            f"{NEON_API_BASE}/projects/{neon_project_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        return True


def mask_connection_string(url: str) -> str:
    """
    Replace the password in a PostgreSQL connection string with '***'.

    Input:  postgresql://user:secretpass@host/db
    Output: postgresql://user:***@host/db
    """
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.password:
        masked = parsed._replace(
            netloc=f"{parsed.username}:***@{parsed.hostname}"
            + (f":{parsed.port}" if parsed.port else "")
        )
        return urlunparse(masked)
    return url
