# Clowdy — Design Decisions & Thinking

This document captures my reasoning for every major decision I made while building Clowdy. Not just what I built, but why I chose one approach over others.

---

## 1. The idea: what even is this?

I wanted to understand how serverless platforms work under the hood. Not at the "read a blog post" level — at the "build every piece yourself" level. AWS Lambda, Vercel Functions, Cloudflare Workers — they all do the same core thing: take user code, run it in isolation, return a result. The rest is UX and scale.

Clowdy is my version of that. A simplified serverless platform where you write Python functions in a web editor, deploy them instantly, and get HTTP endpoints. I'm not trying to compete with AWS — I'm trying to understand what AWS actually does.

The guiding principle: **build every layer yourself, but use managed services where running your own would teach nothing new** (e.g., auth, database hosting).

---

## 2. Backend framework: why FastAPI?

### Options considered

| Framework | Language | Async | Auto docs | Typing |
|---|---|---|---|---|
| **FastAPI** | Python | Yes (native) | Yes (OpenAPI) | Yes (Pydantic) |
| Express.js | Node.js | Yes (callbacks/async) | No (manual) | No (unless TypeScript) |
| Django | Python | Partial (3.1+) | No (DRF adds it) | No |
| Flask | Python | No (needs gevent/async shims) | No (manual) | No |
| Gin / Fiber | Go | Yes | No | Compile-time |

### Why FastAPI

1. **Async is essential**. Docker container operations block for seconds. With a synchronous framework, one invocation would freeze the entire server. FastAPI is async-native — `await asyncio.to_thread(docker_call)` keeps the event loop free.

2. **Pydantic validation for free**. Every request/response has a schema. Instead of writing manual validation (`if "name" not in body: return 400`), I declare a Pydantic model and FastAPI rejects bad requests automatically. That's less code and fewer bugs.

3. **Auto-generated API docs**. FastAPI produces OpenAPI docs at `/docs`. When building a frontend that talks to the API, having an interactive docs page that updates with code changes saved me enormous time.

4. **Python matches the runtime**. The functions users write are Python. The runner script is Python. The Docker SDK has a Python client. Using Python on the backend keeps the whole stack in one language.

5. **Not Django**. Django is great for traditional web apps, but it brings a lot I don't need (admin panel, template engine, form handling, its own ORM opinions). FastAPI is lean — it's just an API framework.

---

## 3. Database (application data): why SQLite?

This is Clowdy's own database for storing projects, functions, invocations, env vars, routes. Not the user-facing databases.

### Options considered

| Database | Setup | Performance | Scaling | Complexity |
|---|---|---|---|---|
| **SQLite** | Zero (file on disk) | Fast for single-server | Single machine | None |
| PostgreSQL | Install/Docker + config | Fast | Multi-machine | Medium |
| MySQL | Install/Docker + config | Fast | Multi-machine | Medium |
| MongoDB | Install/Docker + config | Fast for documents | Multi-machine | Medium |

### Why SQLite

1. **Zero setup**. `sqlite+aiosqlite:///./clowdy.db` — that's the entire database. No Docker container, no port, no credentials, no connection pool tuning. For a learning project that I'm developing solo, this removes an entire category of complexity.

2. **It's enough**. Clowdy is single-user during development. SQLite handles thousands of reads/writes per second. The bottleneck is Docker container startup (~500ms), not database queries (~1ms).

3. **Portability**. The entire database is one file. I can `cp clowdy.db clowdy.db.bak`, share it, or delete it and start fresh. During development, I've blown away the database dozens of times.

4. **Async driver exists**. `aiosqlite` wraps SQLite in an async interface that works with SQLAlchemy's async engine. Same ORM code, same `await db.execute()` pattern — if I ever switch to Postgres, I change one connection string.

### Why not Postgres for the app DB?

I'd switch to Postgres if Clowdy needed multi-user concurrent writes or full-text search. For now, SQLite is simpler and teaches me nothing less about serverless architecture. The interesting part isn't what database I store function metadata in — it's how I execute the functions.

---

## 4. ORM: why SQLAlchemy 2.x?

### Options considered

| ORM | Async | Migration tool | Python typing |
|---|---|---|---|
| **SQLAlchemy 2.x** | Yes (native) | Alembic | `Mapped[type]` |
| SQLAlchemy 1.x | No (greenlet shims) | Alembic | No |
| Tortoise ORM | Yes | Aerich | Some |
| SQLModel | Yes | Alembic | Yes (Pydantic-based) |
| Raw SQL | Yes | Manual | No |

### Why SQLAlchemy 2.x

1. **Async-native**. Version 2.x has proper async support (`AsyncSession`, `AsyncEngine`) instead of the greenlet hacks in 1.x.

2. **Mapped types are clean**. `name: Mapped[str] = mapped_column(index=True)` — the column type, nullability, and Python type are all in one line. Compare to 1.x: `name = Column(String, nullable=False, index=True)` where the Python type is implicit.

3. **Alembic for migrations**. Auto-generates migrations from model changes. I add a field to the model, run `alembic revision --autogenerate`, and Alembic writes the `ALTER TABLE` SQL. I've used this for 7 migrations so far (001–007) and it hasn't failed once.

4. **Industry standard**. SQLAlchemy is the most widely used Python ORM. When I hit a problem, the answer is usually on the first page of search results.

### Why not SQLModel?

SQLModel (by the FastAPI creator) merges Pydantic + SQLAlchemy into one class. Sounds convenient, but it blurs the line between "what I store" and "what I expose in the API." I want separate models (SQLAlchemy) and schemas (Pydantic) because they diverge — the DB stores `database_url` with the real password, but the API response returns a masked version. Keeping them separate makes that natural.

---

## 5. Authentication: why Clerk?

### Options considered

| Auth provider | Self-hosted? | JWT verification | UI components | Free tier |
|---|---|---|---|---|
| **Clerk** | No (SaaS) | JWKS endpoint | React SDK | 10k MAU |
| Auth0 | No (SaaS) | JWKS endpoint | Lock widget | 7.5k MAU |
| Supabase Auth | Yes (or hosted) | JWT secret | React hooks | Unlimited |
| Firebase Auth | No (SaaS) | Google certs | Firebase SDK | Unlimited |
| Roll my own | Yes | N/A | Build it | Free |

### Why Clerk

1. **Auth is not what I'm learning**. Clowdy is about serverless execution, not about bcrypt and session tokens. Clerk handles sign-up, sign-in, MFA, session management — I don't want to build any of that.

2. **Simple backend integration**. The entire backend auth is one file (`auth.py`, 92 lines). It fetches Clerk's public keys (JWKS), verifies the JWT signature, extracts the `sub` claim as `user_id`. That's it. No user table, no password storage, no session management.

3. **React components**. `<SignIn />` and `<SignUp />` are drop-in components. I didn't build a single auth form.

4. **JWKS-based verification**. The backend never talks to Clerk's servers during requests (after initial key fetch). It verifies JWTs locally using cached public keys. No network round-trip per request.

### Why not roll my own?

Because it would be 300+ lines of bcrypt, session tokens, refresh tokens, CSRF protection, email verification — and I'd learn nothing about serverless architecture from any of it. Auth is a solved problem. I'm not solving it again.

---

## 6. Function execution: why Docker containers?

This is the core of the platform. The most important decision.

### Options considered

| Isolation method | Security | Startup time | Resource control | Complexity |
|---|---|---|---|---|
| **Docker containers** | Strong (kernel-level) | ~500ms | Full (cgroups) | Medium |
| subprocess (no isolation) | None | ~10ms | None | Low |
| V8 isolates (Cloudflare model) | Strong | ~5ms | V8-managed | High |
| Firecracker microVMs (AWS model) | Strongest | ~125ms | Full | Very high |
| gVisor | Strong | ~100ms | Full | High |
| WebAssembly (Wasm) | Strong | ~5ms | Wasm-managed | Medium-High |

### Why Docker

1. **User code is untrusted**. Someone could write `import os; os.system("rm -rf /")`. Docker containers run in isolated namespaces — the user's code can't see the host filesystem, processes, or network. Even if they break out of the Python sandbox, they're still inside a container with 128MB RAM, no network, and a 30-second kill timer.

2. **Resource limits are built in**. `mem_limit="128m"`, `nano_cpus=500_000_000`, `network_disabled=True` — three lines in the Docker SDK that enforce hard resource caps. No infinite-loop function can eat more than 128MB or run longer than 30 seconds.

3. **Already installed**. Docker Desktop/Colima is already on my machine. No custom kernel modules, no Firecracker setup, no V8 embedding.

4. **Clean lifecycle**. Create container → copy code in → start → wait → read output → destroy. The container is gone after execution. No state leaks between invocations.

5. **Custom images work naturally**. When a project has pip dependencies, I build a custom Docker image extending the base. `FROM clowdy-python-runtime` + `RUN pip install -r requirements.txt`. Docker's layer caching makes subsequent builds instant if requirements haven't changed.

### Why not subprocesses?

Zero isolation. A user function could read environment variables, access the filesystem, or kill processes. Completely unsuitable for running untrusted code.

### Why not Firecracker?

Firecracker (what AWS Lambda uses) provides stronger isolation than Docker, but it requires KVM (Linux kernel virtualization), a custom root filesystem, and significant setup. It's the right choice at AWS scale. It's overkill for a learning project on a MacBook.

### The design: runner.py

The base Docker image (`python:3.12-slim`) contains a single file: `runner.py`. This script:

1. Reads `INPUT_JSON` from the environment
2. Dynamically imports `/app/function.py` (the user's code, copied in at runtime)
3. Detects whether the handler takes `(input)` or `(event, context)`
4. Calls the handler and prints the result as JSON to stdout
5. The backend captures stdout — that's the function's return value

Why stdout instead of an HTTP server inside the container? Because **containers are ephemeral**. They live for one invocation. Starting an HTTP server inside each container would add latency and complexity. Print to stdout, capture, done.

---

## 7. Frontend: why React + Vite + Tailwind?

### Options considered

| Stack | SSR? | Bundle size | DX |
|---|---|---|---|
| **React + Vite** | No (SPA) | Small (tree-shaken) | Fast HMR |
| Next.js | Yes | Larger | Good but heavier |
| Vue + Vite | No (SPA) | Small | Fast HMR |
| Svelte | No (SPA) | Smallest | Fast |
| Plain HTML/JS | No | Smallest | No tooling |

### Why React + Vite

1. **SPA is fine here**. Clowdy is a dashboard, not a content site. There's no SEO requirement. No server-side rendering needed. A single-page app with client-side routing is the right fit.

2. **Vite over Create React App**. CRA is effectively dead (no updates since 2022). Vite starts in <1 second, HMR is near-instant, and it uses native ES modules during development.

3. **React because it's what I know best**. I've built production apps with React. With Vue or Svelte, I'd be learning a UI framework instead of learning serverless architecture.

4. **Tailwind CSS for rapid styling**. No CSS files to manage, no naming conventions. `className="bg-zinc-900 text-white p-4 rounded-lg"` — the styling is right there in the component. shadcn/ui gives me pre-built components (Button, Card, Input) with Tailwind classes that I can customize.

5. **Monaco Editor**. The code editor in Clowdy is the same editor that powers VS Code. The `@monaco-editor/react` wrapper makes it a single React component. Syntax highlighting, autocomplete, and error markers for free.

### Why not Next.js?

Next.js adds SSR, file-based routing, API routes, and a build server. I don't need any of that. Clowdy's frontend is a pure client-side app that talks to a separate FastAPI backend. Next.js would add complexity for zero benefit.

---

## 8. Code editor: why Monaco?

### Options considered

| Editor | Origin | Features | Bundle size |
|---|---|---|---|
| **Monaco** | VS Code | Full IDE features | ~2MB |
| CodeMirror 6 | Independent | Lightweight, extensible | ~200KB |
| Ace | Cloud9 | Good, aging | ~300KB |
| textarea | Browser | None | 0KB |

### Why Monaco

1. **Users already know it**. Monaco is the engine inside VS Code. The keyboard shortcuts, selections, find/replace — it all works exactly like the editor developers already use daily.

2. **Python support out of the box**. Syntax highlighting, auto-indent, bracket matching, minimap — all without configuration.

3. **Worth the bundle size**. Yes, Monaco is ~2MB. But Clowdy is a developer tool, not a marketing page. The users have fast connections and expect a rich editing experience. A `<textarea>` would make the product feel like a toy.

---

## 9. API Gateway: why route matching with path params?

### Options considered

| Approach | Example | Flexibility |
|---|---|---|
| **Method + path pattern matching** | `GET /users/:id` → extract `{id}` | High |
| Filesystem routing (Next.js style) | `/users/[id].py` | Medium |
| Simple function-to-URL mapping | `/api/invoke/{function_id}` | Low |
| GraphQL | Single endpoint, query-based | High but different |

### Why pattern matching

1. **REST is what APIs look like**. Users deploying APIs want `GET /users/:id`, `POST /users`, `DELETE /users/:id`. Not `/api/invoke/abc123` with a method field in the body.

2. **Path parameter extraction**. The route `/users/:id/posts/:postId` matched against `/users/42/posts/7` produces `{id: "42", postId: "7"}`. This gets passed to the function as `event.params`. The function doesn't need to parse URLs.

3. **Event object pattern**. Gateway invocations produce a structured event:
   ```python
   {
     "method": "GET",
     "path": "/users/42",
     "params": {"id": "42"},
     "query": {"page": "2"},
     "headers": {"content-type": "application/json"},
     "body": null
   }
   ```
   This mirrors what AWS Lambda receives from API Gateway. Functions that work here would conceptually work on AWS too.

4. **`handler(event, context)` dual signature**. The runner auto-detects whether the handler takes one argument (`handler(input)` for simple functions) or two (`handler(event, context)` for gateway functions). Old functions don't break; new gateway functions get richer data.

### Implementation choice: regex-based matching

Each route pattern like `/users/:id` gets compiled into a regex (`^/users/(?P<id>[^/]+)$`). When a request comes in, we iterate through routes, try each regex, and return the first match. Priority: exact method first, then `ANY` as fallback.

This is simple and works. At scale, you'd want a trie/radix tree for O(log n) matching instead of O(n) iteration. But Clowdy projects have <20 routes typically.

---

## 10. Environment variables: why per-project, not per-function?

### Options considered

| Scope | Granularity | UX |
|---|---|---|
| **Per-project** | All functions in project share vars | Simple, one config panel |
| Per-function | Each function has its own vars | Fine-grained but noisy |
| Global | All functions share vars | Too coarse |

### Why per-project

1. **Projects are the deployment unit**. A project represents one "app" — an API with multiple functions. All functions in a project typically need the same API keys, database URLs, and config values.

2. **Real platforms do this**. Vercel, AWS Lambda, and Heroku all scope environment variables to the "project" or "application" level, not per-function.

3. **Secret masking**. Each env var has an `is_secret` flag. When `is_secret=True`, the API returns `"***"` instead of the actual value. The frontend shows a toggle to reveal it. This prevents accidental exposure of API keys in screenshots or screen shares.

### Injection mechanism

When a function is invoked, the invoke router fetches all `EnvVar` rows for the project, builds a `dict[str, str]`, and passes it to `docker_runner.run_function()`. The Docker SDK injects them as container environment variables. The user's code accesses them via `os.environ["KEY"]` — the standard Python way.

---

## 11. pip Dependencies: why build custom Docker images?

### Options considered

| Approach | Speed | Caching | Reliability |
|---|---|---|---|
| **Custom Docker image per project** | First build: ~30-60s, cached: instant | By content hash | High |
| Install at runtime (`pip install` on each invocation) | +10-30s per invocation | None | Fragile |
| Pre-built images with common packages | Instant | Fixed set | Limited |
| Virtual environments mounted as volumes | Medium | By project | Medium |

### Why custom images

1. **Pay the cost once**. The first time a user saves `requirements.txt`, we build a Docker image. Takes 30-60 seconds. After that, every invocation uses the cached image — zero additional latency.

2. **Content-hash caching**. We SHA256 the sorted, stripped requirements. If the hash hasn't changed, we skip the build entirely. Users can click "Save" repeatedly and it won't rebuild. If they change a version number, only then does it rebuild.

3. **Clean layering**. Custom images extend the base: `FROM clowdy-python-runtime`. The user's packages are an additional layer on top. If the base image changes (e.g., security patch), we can rebuild custom images too.

4. **Build errors are visible**. When `pip install` fails (bad package name, version conflict), we capture the Docker `BuildError` log and return the actual pip output:
   ```
   ERROR: Could not find a version that satisfies the requirement nonexistent-package
   ```
   Not a generic "build failed" message.

### The gotcha: `BuildError` handling

Originally, I caught generic `Exception` from Docker builds. When a user tried `requests=2.31.0` (single `=` instead of `==`), they got:
```
Failed to build image: The command '/bin/sh -c pip install...' returned a non-zero code: 1
```
Useless. I fixed this by catching `docker.errors.BuildError` specifically and iterating through `exc.build_log` to extract the actual pip output (last 10 lines of stream/error chunks). Now the user sees what pip actually complained about.

---

## 12. Managed databases: why Neon?

### The need

Functions are stateless — they die after each invocation. But real APIs need to store data. Every serious serverless platform integrates with a database. Clowdy should too.

The goal: one-click database provisioning. User clicks a button, gets a PostgreSQL database, and `DATABASE_URL` is automatically available in all their functions. No configuration.

### Options considered

| Provider | Type | Provisioning speed | Free tier | API quality |
|---|---|---|---|---|
| **Neon** | Serverless Postgres | ~5-10s | Generous | Excellent (REST v2) |
| Supabase | Managed Postgres + extras | ~60-120s | 2 projects only | OK |
| PlanetScale | Serverless MySQL (Vitess) | N/A | Removed (2024) | Good |
| CockroachDB | Distributed SQL | Manual | Generous | Undocumented |
| Railway / Render | Managed Postgres | N/A | Removed / 90-day expiry | Minimal |
| Self-hosted (Docker) | Postgres in container | Instant | Free | N/A |

### Why Neon

1. **Fast provisioning**. ~5-10 seconds to create a project and get a connection URI. Supabase takes 1-2 minutes. For a "one-click" experience, 5 seconds is acceptable; 2 minutes is not.

2. **Clean API**. Three API calls: get org ID, create project, get connection URI. That's the entire provisioning flow. Supabase requires polling for readiness.

3. **Serverless-native**. Neon scales compute to zero when idle. This matches Clowdy's model — functions don't run when nobody invokes them, and the database shouldn't consume resources when nobody queries it.

4. **Real PostgreSQL**. Not "compatible" — actual Postgres. `psycopg2.connect(os.environ["DATABASE_URL"])` works with every Postgres feature.

5. **Free tier works for per-project provisioning**. With Neon organizations, one API key can manage multiple projects.

### Why not Supabase?

Supabase is great, but provisioning takes 60-120 seconds and the free tier is limited to 2 projects. Clowdy creates one Neon project per Clowdy project — Supabase's limit would be hit immediately.

### Why not self-hosted Postgres?

Running Postgres in Docker is free, but:
- Networking is complex — function containers need to reach the Postgres container, which means a shared Docker network and disabling `network_disabled=True` for those functions.
- One Postgres per project is resource-heavy. One shared Postgres with per-project databases is a single point of failure.
- The point of Clowdy is learning cloud service integration, not running my own Postgres.

### Implementation

- **Backend service** (`neon_service.py`): Three functions — `provision_database()`, `deprovision_database()`, `mask_connection_string()`. Uses `httpx.AsyncClient` for non-blocking calls to Neon API v2.
- **Router** (`routers/database.py`): GET status, POST provision, DELETE deprovision. All ownership-checked.
- **Injection**: `invoke.py` and `gateway.py` check `project.database_url` and pass it to `docker_runner.run_function()` as an env var.
- **Security**: The API never returns unmasked passwords. `mask_connection_string()` replaces the password with `***` using `urlparse`.

---

## 13. AI assistant: why Groq + Llama?

### Options considered

| Provider | Model | Speed | Cost | Tool calling |
|---|---|---|---|---|
| **Groq** | Llama 4 Scout 17B | Very fast (~1s) | Free tier | Yes |
| OpenAI | GPT-4 / GPT-4o | Medium | Paid | Yes |
| Anthropic | Claude 3.5 / Opus | Medium | Paid | Yes |
| Ollama (local) | Various | Slow (depends on HW) | Free | Limited |
| Google | Gemini | Medium | Free tier | Yes |

### Why Groq

1. **Free**. Groq has a free tier with generous rate limits. This is a learning project — paying per API call for the AI feature doesn't make sense.

2. **Fast inference**. Groq runs on custom LPU hardware. Responses come back in ~1 second. The AI assistant feels responsive, not sluggish.

3. **Tool calling works**. The AI assistant doesn't just chat — it calls tools. "Create a function that reverses a string" triggers a `create_function` tool call. Groq's Llama models support structured tool calling reliably.

4. **No API key requirements beyond Groq**. No OpenAI billing setup, no Anthropic waitlist. Get a key at console.groq.com, paste it in `.env.local`, done.

### Tool calling architecture

The AI agent has 6 tools: `create_function`, `list_functions`, `invoke_function`, `view_logs`, `update_function`, `delete_function`. Each tool is defined as a JSON Schema that the model reads.

The loop:
1. User message → Groq (with tool definitions)
2. Groq responds with a tool call (e.g., `create_function({name: "greeter", code: "..."})`)
3. Backend executes the tool against the real database
4. Tool result → Groq
5. Groq writes a human-readable response summarizing what it did

This is the same pattern as ChatGPT plugins and Claude's tool use. The AI translates natural language into structured API calls.

---

## 14. Alembic: why auto-run migrations on startup?

### The choice

Instead of requiring `alembic upgrade head` as a separate step, Clowdy runs migrations automatically in the FastAPI `lifespan` handler at startup.

### Why

1. **Can't forget**. During development, I've added 7 migrations. If migrations required a manual step, I'd forget every time and get "column not found" errors until I remembered.

2. **Alembic is idempotent**. `upgrade head` checks which migrations have already run and only applies new ones. Running it on every startup costs ~50ms and changes nothing if the schema is current.

3. **First-time setup is one command**. `./venv/bin/uvicorn app.main:app --reload` creates the database and applies all migrations. No separate setup script.

---

## 15. Global exception handler: why?

FastAPI's CORS middleware doesn't add headers to responses from unhandled exceptions. If a route handler throws an unexpected error, the browser gets a CORS error instead of the actual error message.

I added a global `@app.exception_handler(Exception)` that catches unhandled exceptions and returns them as a JSONResponse. Since JSONResponse goes through the middleware pipeline, it gets CORS headers. The frontend sees the actual error message instead of "Network Error."

---

## 16. Docker client: why the Colima handling?

On macOS, Docker Desktop puts the socket at `/var/run/docker.sock`. But I use Colima (a lightweight Docker VM alternative), which puts it at `~/.colima/default/docker.sock`. The Docker SDK's `docker.from_env()` doesn't find it automatically.

`_get_docker_client()` in `docker_runner.py` checks three locations in order:
1. `DOCKER_HOST` environment variable (explicit override)
2. `~/.colima/default/docker.sock` (Colima on macOS)
3. Default (`docker.from_env()`)

It's a small quality-of-life detail, but without it, every Docker call would fail on my machine.

---

## 17. What I'd do differently at production scale

These are things I deliberately skipped because they'd add complexity without teaching me more about serverless architecture:

1. **Container pooling**. Right now, every invocation creates and destroys a container. AWS Lambda keeps "warm" containers for subsequent calls. This would cut invocation latency from ~500ms to ~50ms.

2. **Postgres instead of SQLite**. For concurrent multi-user access, SQLite's single-writer lock becomes a bottleneck. Postgres with connection pooling would be the production choice.

3. **Secrets management**. Database URLs and env var values are stored in plaintext in SQLite. Production would use Vault or AWS Secrets Manager.

4. **Async provisioning**. Database and image builds currently block the request. Production would return "provisioning" status immediately and use background workers + webhooks.

5. **Event-driven invocations**. Right now, functions are only triggered by HTTP requests. Real serverless platforms support cron schedules, queue events, database triggers, etc.

6. **Multi-language runtimes**. Currently Python-only. Adding Node.js would mean a second base image, a second runner script, and runtime detection in the invoke flow.

7. **Observability**. Structured logging, OpenTelemetry traces, Prometheus metrics. Currently there's `print()` debugging and invocation logs in SQLite.

8. **Rate limiting**. No protection against abuse. A user could invoke functions in a tight loop and exhaust Docker resources. Production would need per-user rate limits and concurrent invocation caps.
