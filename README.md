# Clowdy

A simplified serverless function platform inspired by AWS Lambda. Write Python functions in a web editor, deploy them instantly, and get HTTP endpoints to invoke them. Organize functions into projects with environment variables, pip dependencies, managed databases, and an API gateway, all from a single dashboard.

Built to learn how serverless cloud infrastructure works under the hood.

## Table of Contents

- [How It Works](#how-it-works)
- [Features](#features)
- [Comparison to Vercel and AWS](#comparison-to-vercel-and-aws)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup Guide](#setup-guide)
- [API Endpoints](#api-endpoints)
- [Security Model](#security-model)
- [Contributing](#contributing)

## How It Works

```
Write Python code in Monaco editor (browser)
                    |
                    v
       Save to SQLite via FastAPI
                    |
          +---------+---------+
          |                   |
     Direct invoke       Gateway invoke
  POST /api/invoke/:id   ANY /api/gateway/:slug/:path
          |                   |
          |              Match route (method + path pattern)
          |              Extract path params (:id -> {id: "123"})
          |                   |
          +---------+---------+
                    |
                    v
         Create Docker container
         (clowdy-python-runtime or custom image with pip deps)
                    |
                    v
         Inject into container:
         - User code as /app/function.py
         - Input data as INPUT_JSON env var
         - Project env vars (KEY=value)
         - DATABASE_URL (if Neon database provisioned)
                    |
                    v
         Run with resource limits:
         - 128MB RAM, 0.5 CPU, no network, 30s timeout
                    |
                    v
         Capture stdout (JSON result)
         Destroy container
                    |
                    v
         Log invocation (input, output, status, duration)
         Return result to caller
```

## Features

- **Projects**: Organize functions into projects with auto-generated URL slugs. Each project gets its own environment variables, pip dependencies, database, and API routes.

- **Functions**: Create, edit, and delete Python functions through a Monaco code editor (same editor as VS Code). Test functions with JSON input directly from the browser and see results immediately.

- **API Gateway**: Map HTTP routes to functions using method + path patterns with parameter extraction. Define routes like `GET /users/:id` and Clowdy matches incoming requests, extracts parameters, and invokes the right function with a structured event object containing method, path, params, query, headers, and body.

- **Environment Variables**: Per-project key-value pairs injected into function containers at runtime. Mark variables as secret to hide values in the UI. Access them via `os.environ["KEY"]` in your functions.

- **pip Dependencies**: Per-project `requirements.txt` support. When you save dependencies, Clowdy builds a custom Docker image extending the base runtime with your packages installed. Images are cached by content hash -- unchanged requirements skip the build.

- **Managed Databases**: One-click PostgreSQL database provisioning via Neon. The connection string is automatically injected as `DATABASE_URL` into every function container in the project. No configuration needed -- just `import psycopg2; conn = psycopg2.connect(os.environ["DATABASE_URL"])`.

- **AI Assistant**: Chat panel powered by Groq (Llama 4 Scout) with tool calling. The AI can create, invoke, update, delete, and inspect functions through natural language. Ask it to "create a function that reverses a string" and it writes the code, deploys it, and gives you the invoke URL.

- **Invocation Logs**: Every function execution is logged with input data, output data, status (success/error/timeout), duration in milliseconds, source (direct or gateway), and HTTP method/path for gateway calls. View the 50 most recent logs per function.

- **Dashboard**: Overview stats showing total functions, total invocations, success rate percentage, and average execution duration. Quick access to recent projects.

## Comparison to Vercel and AWS

| Dimension | Clowdy | Vercel Serverless Functions | AWS Lambda |
|---|---|---|---|
| Runtimes | Python | Node.js, Python, Go, Ruby | 7+ languages |
| Isolation | Docker containers | V8 isolates / microVMs | Firecracker microVMs |
| API Gateway | Built-in route matching with path params | Filesystem routing (Next.js) | Separate API Gateway service |
| Env vars | Per-project UI with secret masking | Dashboard per-environment | Console / SSM / Secrets Manager |
| Database | One-click Neon PostgreSQL | Neon/Supabase integration (separate) | RDS/DynamoDB (separate services) |
| AI assistant | Built-in (create/invoke/manage functions) | None | Amazon Q (separate service) |
| Code editor | Built-in Monaco editor | None (deploy from repo) | AWS Cloud9 (separate service) |
| Auth | Clerk JWT | Vercel Auth | IAM / Cognito |
| Pricing | Free (self-hosted) | Free tier, then per-invocation | Free tier, then per-invocation |
| Use case | Learning, prototyping | Production web apps | Production at scale |

Clowdy is not a production competitor to Vercel or AWS. It is a learning project that implements the core concepts of serverless platforms in a simple, understandable codebase.

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | React 19, TypeScript, Vite | SPA framework and build tool |
| Styling | Tailwind CSS v4, shadcn/ui | Utility-first CSS and component library |
| Routing | React Router v7 | Client-side page routing |
| Code Editor | Monaco Editor (React) | In-browser Python code editing |
| Auth (Frontend) | Clerk React SDK | Sign-in/sign-up UI and JWT tokens |
| Backend | FastAPI, Python 3.10+ | Async API framework |
| ORM | SQLAlchemy 2.x (async) | Database models and queries |
| Database | SQLite (aiosqlite) | Application data storage |
| Migrations | Alembic | Schema versioning (auto-runs on startup) |
| Validation | Pydantic | Request/response schema validation |
| Auth (Backend) | PyJWT + Clerk JWKS | JWT signature verification |
| Execution | Docker SDK for Python | Container lifecycle management |
| Runtime Image | python:3.12-slim | Base image for function containers |
| AI | Groq API (Llama 4 Scout) | LLM with tool calling for the AI assistant |
| Managed DB | Neon REST API v2 | PostgreSQL database provisioning |
| HTTP Client | httpx | Async HTTP calls to Neon API |

## Project Structure

```
clowdy/
  backend/
    app/
      main.py                    # FastAPI app, lifespan, CORS, router registration
      auth.py                    # Clerk JWT verification (get_current_user)
      config.py                  # Environment variables (GROQ, CLERK, NEON keys)
      database.py                # SQLAlchemy async engine and session
      models.py                  # ORM models (Project, Function, Invocation, EnvVar, Route)
      schemas.py                 # Pydantic request/response schemas
      routers/
        projects.py              # Project CRUD
        functions.py             # Function CRUD
        invoke.py                # Function execution and invocation logs
        chat.py                  # AI agent chat endpoint
        env_vars.py              # Environment variable management
        routes.py                # HTTP route definitions
        requirements.py          # pip dependency management
        database.py              # Neon database provisioning
        gateway.py               # HTTP API gateway with route matching
      services/
        docker_runner.py         # Docker container execution logic
        ai_agent.py              # Groq integration and tool definitions
        image_builder.py         # Custom Docker image building for pip deps
        neon_service.py          # Neon PostgreSQL API client
    docker/
      runtimes/
        python/
          Dockerfile             # Base runtime image (python:3.12-slim)
          runner.py              # Wrapper that imports and calls handler()
    alembic/
      versions/                  # 7 migration files (001-007)
    requirements.txt             # Python dependencies
    .env.local                   # API keys (git-ignored)

  frontend/
    src/
      pages/
        Dashboard.tsx            # Home screen with stats
        Projects.tsx             # Project list
        CreateProject.tsx        # New project form
        ProjectDetail.tsx        # Project management (6 tabs)
        Functions.tsx            # Function list
        CreateFunction.tsx       # New function form
        FunctionDetail.tsx       # Function editor, test panel, logs
      components/
        ui/                      # shadcn/ui (button, card, input, label, badge)
        layout/                  # Layout, Sidebar
        functions/               # FunctionCard, CodeEditor (Monaco wrapper)
        projects/                # ProjectCard
        chat/                    # ChatPanel, ChatMessage
        auth/                    # AuthProvider (Clerk)
      lib/
        api.ts                   # Typed API client with Clerk JWT injection
    package.json
    vite.config.ts
    tsconfig.json
```

## Setup Guide

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (Docker Desktop, Colima, or similar)
- [Clerk](https://dashboard.clerk.com) account (for authentication)
- [Groq](https://console.groq.com) account (free, for AI assistant)
- [Neon](https://console.neon.tech) account (free, optional, for managed databases)

### Backend

```bash
cd backend

# Create virtual environment and install dependencies
python -m venv venv
./venv/bin/pip install -r requirements.txt

# Build the base Docker runtime image
cd docker/runtimes/python
docker build -t clowdy-python-runtime .
cd ../../..

# Create .env.local with your API keys
cat > .env.local << 'EOF'
GROQ_API_KEY=gsk_your_key_here
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
NEON_API_KEY=your_neon_api_key_here
EOF

# Start the development server
./venv/bin/uvicorn app.main:app --reload
```

The backend runs at http://localhost:8000. Interactive API docs at http://localhost:8000/docs.

Alembic migrations run automatically on startup -- the database schema is always up to date.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend runs at http://localhost:5173.

### Verify

```bash
# Health check
curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
```

### Environment Variables Reference

**Backend** (`backend/.env.local`):

| Variable | Required | Default | Source |
|---|---|---|---|
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./clowdy.db` | -- |
| `FRONTEND_URL` | No | `http://localhost:5173` | -- |
| `GROQ_API_KEY` | Yes | -- | https://console.groq.com/keys |
| `CLERK_JWKS_URL` | Yes | -- | Clerk dashboard > API Keys |
| `NEON_API_KEY` | No | -- | https://console.neon.tech/account/api-keys |

**Frontend** (`frontend/.env.local`):

| Variable | Required | Default |
|---|---|---|
| `VITE_API_URL` | No | `http://localhost:8000` |

## API Endpoints

### Health and Stats

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | No | Health check |
| GET | `/api/stats` | Yes | Dashboard statistics |

### Projects

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/projects` | Yes | Create a project |
| GET | `/api/projects` | Yes | List all projects |
| GET | `/api/projects/:id` | Yes | Get a project |
| PUT | `/api/projects/:id` | Yes | Update a project |
| DELETE | `/api/projects/:id` | Yes | Delete a project |
| GET | `/api/projects/:id/functions` | Yes | List functions in a project |

### Functions

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/functions` | Yes | Create a function |
| GET | `/api/functions` | Yes | List all functions |
| GET | `/api/functions/:id` | Yes | Get a function |
| PUT | `/api/functions/:id` | Yes | Update a function |
| DELETE | `/api/functions/:id` | Yes | Delete a function |

### Invocation

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/invoke/:id` | No | Invoke a function |
| GET | `/api/functions/:id/invocations` | No | List invocation logs |

### AI Chat

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/chat` | Yes | Chat with the AI assistant |

### Environment Variables

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/projects/:id/env` | Yes | List env vars |
| POST | `/api/projects/:id/env` | Yes | Set an env var (upsert) |
| DELETE | `/api/projects/:id/env/:key` | Yes | Delete an env var |

### Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/projects/:id/routes` | Yes | List routes |
| POST | `/api/projects/:id/routes` | Yes | Create a route |
| PUT | `/api/projects/:id/routes/:routeId` | Yes | Update a route |
| DELETE | `/api/projects/:id/routes/:routeId` | Yes | Delete a route |

### Dependencies

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/projects/:id/requirements` | Yes | Get requirements and build status |
| PUT | `/api/projects/:id/requirements` | Yes | Update requirements and rebuild image |

### Database

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/projects/:id/database` | Yes | Get database status |
| POST | `/api/projects/:id/database/provision` | Yes | Provision a Neon database |
| DELETE | `/api/projects/:id/database/deprovision` | Yes | Delete the Neon database |

### API Gateway

| Method | Path | Auth | Description |
|---|---|---|---|
| ANY | `/api/gateway/:slug` | No | Route to project root |
| ANY | `/api/gateway/:slug/*path` | No | Route with path matching |

## Security Model

### Container Isolation

Every function runs in an ephemeral Docker container with strict limits:

- **No network** -- `network_disabled=True` prevents all outbound connections
- **Memory cap** -- 128MB limit prevents memory exhaustion
- **CPU cap** -- 0.5 cores prevents CPU monopolization
- **Timeout** -- 30 seconds maximum, container killed after
- **No volume mounts** -- code copied via `put_archive`, no host filesystem access
- **Ephemeral** -- container destroyed after every execution, no persistent state

### Authentication

- Protected endpoints require a valid Clerk JWT in the `Authorization: Bearer <token>` header
- Backend verifies token signatures using Clerk's JWKS endpoint (RS256)
- User ID extracted from the token's `sub` claim
- Each user can only see and manage their own projects and functions

### Public Endpoints

These endpoints are intentionally public (no auth required):

- `/api/health` -- health check
- `/api/invoke/:id` -- function invocation (anyone with the function ID can invoke)
- `/api/gateway/:slug/*` -- API gateway (anyone with the project slug can call routes)
- `/api/functions/:id/invocations` -- invocation logs

### Secret Handling

- Environment variables marked as `secret` display as `****` in the UI
- Database connection strings have passwords replaced with `***` in API responses
- Real values are always injected into function containers at runtime

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run the backend (`./venv/bin/uvicorn app.main:app --reload`) and frontend (`npm run dev`) to verify
5. Commit and push
6. Open a pull request

### Code Style

- **No emojis** in code, comments, or commit messages
- **Python**: type hints, async/await, Black formatting
- **TypeScript**: strict mode, explicit types for API responses

### Adding a New Router

1. Create `backend/app/routers/your_router.py` with an `APIRouter`
2. Import and register it in `backend/app/main.py`
3. Add Pydantic schemas in `backend/app/schemas.py`
4. Add TypeScript types and API methods in `frontend/src/lib/api.ts`

### Adding a Migration

```bash
cd backend
./venv/bin/alembic revision -m "description_of_change"
```

Edit the generated file in `alembic/versions/`, then restart the server -- migrations run automatically on startup.
