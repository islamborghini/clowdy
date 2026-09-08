"""
Seed the read-only demo with content worth looking at.

An empty demo is a broken demo: with nothing deployed there is no invocation
to run, no warm pool to fill, and the cluster page shows three idle workers
doing nothing. This creates a project and four functions chosen to exercise a
different part of the platform each.

Idempotent -- running it twice changes nothing, so cloud-init can call it on
every boot without special-casing the first one.

    docker compose exec -T control-plane python -m app.seed_demo
"""

import asyncio

from sqlalchemy import select

from app.config import DEMO_USER_ID
from app.database import async_session
from app.models import Function, FunctionVersion, Project, Route

PROJECT_SLUG = "demo"

FUNCTIONS = [
    {
        "id": "demo-hello",
        "name": "hello",
        "description": "The smallest thing that works. Returns a greeting.",
        "code": '''def handler(event):
    """Return a greeting. Try changing the name in the input below."""
    name = event.get("name", "world")
    return {"message": f"Hello, {name}!"}
''',
    },
    {
        "id": "demo-fib",
        "name": "fibonacci",
        "description": "Real CPU work. Compare the first call to the second to see warm reuse.",
        "code": '''def handler(event):
    """Compute fibonacci(n) iteratively.

    Worth invoking twice. The first call pays a cold start while a container
    is created; every call after it execs into the warm container and is
    roughly an order of magnitude faster.
    """
    n = min(int(event.get("n", 30)), 500)
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {"n": n, "result": a}
''',
    },
    {
        "id": "demo-load",
        "name": "burn",
        "description": "Occupies a worker slot for a moment. Used to demonstrate backpressure.",
        "code": '''import time


def handler(event):
    """Hold an execution slot briefly.

    Fire enough of these at once and the fleet runs out of concurrency, at
    which point the platform returns 503 rather than queueing. Watch the
    Cluster page while a load test runs.
    """
    seconds = min(float(event.get("seconds", 0.5)), 5.0)
    time.sleep(seconds)
    return {"slept": seconds}
''',
    },
    {
        "id": "demo-http",
        "name": "http_echo",
        "description": "Gateway example. Reachable at /api/gateway/demo/echo/:id",
        "code": '''def handler(event, context):
    """Echo back the HTTP request the gateway parsed.

    Called through the gateway, the event carries the full request: method,
    path, extracted path params, query string, headers, and body. Returning
    a dict with statusCode/headers/body controls the HTTP response.
    """
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": {
            "method": event["method"],
            "path": event["path"],
            "params": event["params"],
            "query": event["query"],
            "ran_on": context["function_name"],
        },
    }
''',
    },
]

ROUTES = [
    {"function_id": "demo-http", "method": "GET", "path": "/echo/:id"},
    {"function_id": "demo-hello", "method": "GET", "path": "/hello"},
]


async def seed() -> None:
    async with async_session() as db:
        existing = await db.execute(
            select(Project).where(Project.slug == PROJECT_SLUG)
        )
        if existing.scalar_one_or_none():
            print("Demo content already present, nothing to do.")
            return

        project = Project(
            id="demo-project",
            user_id=DEMO_USER_ID,
            name="Demo",
            slug=PROJECT_SLUG,
            description="Example functions for the public demo.",
        )
        db.add(project)

        for spec in FUNCTIONS:
            db.add(
                Function(
                    id=spec["id"],
                    user_id=DEMO_USER_ID,
                    project_id=project.id,
                    name=spec["name"],
                    description=spec["description"],
                    active_version=1,
                )
            )
            db.add(
                FunctionVersion(
                    function_id=spec["id"], version=1, code=spec["code"]
                )
            )

        for route in ROUTES:
            db.add(Route(project_id=project.id, **route))

        await db.commit()
        print(f"Seeded {len(FUNCTIONS)} functions and {len(ROUTES)} routes.")


if __name__ == "__main__":
    asyncio.run(seed())
