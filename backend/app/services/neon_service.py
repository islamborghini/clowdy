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


def _raise_with_detail(resp: httpx.Response) -> None:
    """Raise an error with the actual Neon API error message."""
    try:
        body = resp.json()
        message = body.get("message", "") or body.get("error", "") or resp.text
    except Exception:
        message = resp.text
    raise RuntimeError(f"Neon API error ({resp.status_code}): {message}")


async def _get_org_id(client: httpx.AsyncClient) -> str:
    """Fetch the user's Neon organization ID (required for project creation)."""
    resp = await client.get(
        f"{NEON_API_BASE}/users/me/organizations",
        headers=_headers(),
    )
    if resp.status_code != 200:
        _raise_with_detail(resp)
    orgs = resp.json().get("organizations", [])
    if not orgs:
        raise RuntimeError("No Neon organization found. Create one at console.neon.tech")
    return orgs[0]["id"]


async def provision_database(project_name: str) -> tuple[str, str]:
    """
    Create a Neon project and return (neon_project_id, connection_uri).

    Creates a project named 'clowdy-{project_name}' with the default
    database (neondb) and role (neondb_owner).
    """
    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Get the org_id (required by Neon for project creation)
        org_id = await _get_org_id(client)

        # Step 2: Create the Neon project
        create_resp = await client.post(
            f"{NEON_API_BASE}/projects",
            headers=_headers(),
            json={"project": {"name": f"clowdy-{project_name}", "org_id": org_id}},
        )
        if create_resp.status_code != 201:
            _raise_with_detail(create_resp)
        project_data = create_resp.json()
        neon_project_id = project_data["project"]["id"]

        # Step 3: Get the connection URI
        uri_resp = await client.get(
            f"{NEON_API_BASE}/projects/{neon_project_id}/connection_uri",
            headers=_headers(),
            params={
                "database_name": "neondb",
                "role_name": "neondb_owner",
            },
        )
        if uri_resp.status_code != 200:
            _raise_with_detail(uri_resp)
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
        if resp.status_code >= 400:
            _raise_with_detail(resp)
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
