# Clowdy

A serverless function platform, built to understand how one actually works.
Write Python in a browser editor, deploy it, and get an HTTP endpoint. Behind
that, functions run in a fleet of worker nodes with warm container reuse,
consistent-hash placement, and real failover -- the parts of AWS Lambda that
are interesting, implemented rather than described.

It runs two ways from the same codebase: `uvicorn app.main:app` on a laptop is
a complete single-node platform, and `docker compose up` is a distributed one
with a load balancer, two control-plane replicas, and three workers.

**Architecture writeup: [docs/architecture.md](docs/architecture.md).**
Design decisions and the options rejected along the way:
[docs/thinking.md](docs/thinking.md).

## Table of Contents

- [How It Works](#how-it-works)
- [Distributed Execution](#distributed-execution)
- [Features](#features)
- [Comparison to Vercel and AWS](#comparison-to-vercel-and-aws)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup Guide](#setup-guide)
- [Running the Cluster](#running-the-cluster)
- [Deploying to AWS](#deploying-to-aws)
- [Hosting a Public Demo](#hosting-a-public-demo)
- [API Endpoints](#api-endpoints)
- [Security Model](#security-model)
- [Testing](#testing)
- [Contributing](#contributing)

## How It Works

```
Write Python code in Monaco editor (browser)
                    |
                    v
       Save to SQLite via FastAPI
       (each save creates a new FunctionVersion row;
        the function points at its active_version)
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
         Resolve execution context
         (env vars, custom image, DATABASE_URL)
                    |
                    v
         Invoke Service orchestrates the call
                    |
          +---------+---------+
          |                   |
   Assignment Service    Placement Service
   (warm container       (cold start: build image
    pool, keyed by        if needed, create new
    image+network)        container)
          |                   |
          +---------+---------+
                    |
                    v
                Worker Service
         (docker exec into the container)
                    |
                    v
         Inject into container:
         - Active version code as /app/function.py
         - Input data as INPUT_JSON env var
         - Project env vars (KEY=value)
         - DATABASE_URL (if Neon database provisioned)
                    |
                    v
         Run with resource limits:
         - 128MB RAM, 0.5 CPU, 30s timeout
         - Network: disabled by default,
           opt-in per function via toggle
                    |
                    v
         Capture stdout (JSON result)
         Release container back to warm pool
         (or destroy if pool is full)
                    |
                    v
         Log invocation (input, output, status, duration)
         Return result to caller
```

## Distributed Execution

The part of this project worth reading the code for.

**Two planes, one image.** The control plane (`app.main`) is stateless HTTP:
auth, CRUD, gateway routing, and deciding where work goes. The data plane
(`app.worker.main`) owns a Docker daemon and a warm container pool and knows
nothing about users or projects. They ship as the same container image with
different commands, so they cannot drift apart.

**Placement is not round-robin.** Each worker holds its own warm containers
keyed by `(image, network)`, so where a request lands decides whether it costs
20ms or 700ms. Round-robin turns one warm pool into N cold starts. Clowdy uses
consistent hashing with bounded loads: hash the image onto a ring for warm
affinity, then walk past any worker already carrying more than 1.25x its fair
share. Affinity when there is room, spillover when there is not.

**Failure detection is a TTL.** Workers heartbeat into Redis every 5 seconds
with a 15 second expiry. A crashed worker's key expires and it leaves the ring.
No gossip, no leader election, no consensus.

**Saturation returns 503, not a queue.** The scheduler refuses to place work on
a full worker, and the worker independently refuses work past its own
concurrency limit -- its load as seen by the control plane is always slightly
stale, so it enforces the invariant itself.

**It degrades instead of breaking.** No workers registered means the control
plane executes in its own process. That is not a special dev mode; it is the
same fallback that keeps the API serving if the whole fleet disappears.

Watch it work:

```bash
docker compose up --build
python scripts/loadtest.py <function_id> --url http://localhost:8080 -n 300 -c 30
```

which reports latency percentiles, cold-start rate, and how the invocations
actually distributed across the fleet. 200 invocations at the fleet's full
concurrency of 12, on a 4-CPU Colima VM:

```
  mode           distributed
  wall clock     4.00s
  throughput     50.0 req/s
  succeeded      200/200
  latency  p50   181 ms
           p95   1114 ms
  cold starts    12 (6.0%)

  placement
    0f09a6569ff7     71   35.5%  ##############
    c0cb7fdfa75b     67   33.5%  #############
    169b35411e4b     62   31.0%  ############

  imbalance      13.5% (max-min spread over mean)
```

Twelve cold starts is exactly one per concurrent slot: the pools fill once and
every later invocation is warm. Push past the fleet's capacity and it sheds
instead of queueing -- at 30 concurrent, 48 succeed and 102 come back 503, with
no failed executions. The same view renders live at `/cluster` while a load
test runs.

## Features

- **Distributed execution**: Functions run on a fleet of worker nodes chosen by
  a consistent-hash scheduler with warm-container affinity, with automatic
  failover between nodes and backpressure when the fleet is saturated. See
  [Distributed Execution](#distributed-execution).

- **Warm container pool**: Containers stay alive between invocations and are
  reused across any function sharing a runtime image, bounded by pool size,
  idle timeout, and LRU eviction. A warm invocation skips container creation
  entirely.

- **Cluster view**: A live page showing every registered worker, its current
  concurrency, warm containers, share of invocations, and the placement policy
  in effect. Refreshes every two seconds.

- **Projects**: Organize functions into projects with auto-generated URL slugs. Each project gets its own environment variables, pip dependencies, database, and API routes.

- **Functions**: Create, edit, and delete Python functions through a Monaco code editor (same editor as VS Code). Test functions with JSON input directly from the browser and see results immediately.

- **Function Versions**: Every code save creates a new immutable version. A version dropdown in the editor lets you browse previous versions and roll back instantly by setting an older version as active -- no redeploy step. Each version stores its full code snapshot in the `function_versions` table.

- **Per-Function Network Toggle**: Functions run with `network_disabled=True` by default. Flip the toggle in the function detail page to allow outbound network access for that specific function (for calling third-party APIs, fetching data, etc.). The warm container pool keys on network setting so toggling does not bleed network state between functions.

- **Warm Container Pool**: An AWS Lambda-style invocation pipeline split into Assignment Service (warm container pool with LRU eviction and idle reaper), Placement Service (cold start container creation), and Worker Service (`docker exec` into a container to run user code). Warm hits skip container creation entirely, dramatically reducing per-invocation latency.

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
| Warm reuse | Warm pool per worker, LRU + idle reaper | Yes | Yes |
| Placement | Consistent hash on image, bounded load | Managed | Worker Manager + consistent hashing |
| Scaling | Worker ASG / `--scale worker=N` | Automatic | Automatic |
| Backpressure | 503 at fleet capacity | Managed | Reserved concurrency + throttling |
| API Gateway | Built-in route matching with path params | Filesystem routing (Next.js) | Separate API Gateway service |
| Versioning | Auto-versioned, one-click rollback | Git commit per deploy | Versions + aliases |
| Warm starts | Container pool (Assignment Service) | V8 isolate reuse | Firecracker microVM reuse |
| Network egress | Per-function toggle (default off) | Always on | VPC config / always on |
| Env vars | Per-project UI with secret masking | Dashboard per-environment | Console / SSM / Secrets Manager |
| Database | One-click Neon PostgreSQL | Neon/Supabase integration (separate) | RDS/DynamoDB (separate services) |
| AI assistant | Built-in (create/invoke/manage functions) | None | Amazon Q (separate service) |
| Code editor | Built-in Monaco editor | None (deploy from repo) | AWS Cloud9 (separate service) |
| Auth | Clerk JWT | Vercel Auth | IAM / Cognito |
| Pricing | Free (self-hosted) | Free tier, then per-invocation | Free tier, then per-invocation |
| Use case | Learning, prototyping | Production web apps | Production at scale |

Clowdy is not a production competitor to Vercel or AWS. It is a learning
project that implements the core concepts of a serverless platform -- warm
container reuse, application-aware placement, service discovery, failover, and
backpressure -- in a codebase small enough to read in an afternoon.
[docs/architecture.md](docs/architecture.md#what-is-deliberately-not-built) is
explicit about where the simplifications are.

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
| HTTP Client | httpx | Async calls to workers and the Neon API |
| Cluster state | Redis | Worker registry, heartbeats, in-flight counters |
| Control-plane DB | PostgreSQL (clustered) / SQLite (single node) | Application data |
| Load balancer | nginx (`least_conn`) | Distributes across control-plane replicas |
| Orchestration | Docker Compose | Local multi-node topology |
| Infrastructure | Terraform | ECS Fargate, EC2 ASG, ALB, RDS, ElastiCache, ECR |
| CI | GitHub Actions | Tests, builds, migration round-trip, `terraform validate` |

## Project Structure

```
clowdy/
  docker-compose.yml             # The full distributed topology
  backend/
    Dockerfile                   # One image, two roles (control plane / worker)
    app/
      main.py                    # Control plane: lifespan, CORS, routers
      auth.py                    # Clerk JWT verification
      config.py                  # Environment and cluster configuration
      database.py                # SQLAlchemy async engine and session
      models.py                  # ORM models (Project, Function, FunctionVersion, Invocation, EnvVar, Route)
      schemas.py                 # Pydantic request/response schemas
      worker/
        main.py                  # Data plane: POST /run, GET /health, heartbeat
      routers/
        projects.py              # Project CRUD
        functions.py             # Function CRUD + version listing and rollback
        invoke.py                # Function execution and invocation logs
        gateway.py               # HTTP API gateway with route matching
        cluster.py               # Live fleet state and placement policy
        chat.py                  # AI agent chat endpoint
        env_vars.py              # Environment variable management
        routes.py                # HTTP route definitions
        requirements.py          # pip dependency management
        database.py              # Neon database provisioning
        gateway.py               # HTTP API gateway with route matching
      services/                  # AWS Lambda-style execution pipeline
        invoke_service.py        # Orchestrator: warm-or-cold path, exec, release
        assignment_service.py    # Warm container pool, LRU eviction, idle reaper
        placement_service.py     # Cold start container creation
        worker_service.py        # docker exec runner (no container lifecycle)
        context.py               # Resolves env vars, image, DATABASE_URL per invoke
        image_builder.py         # Custom Docker image building for pip deps
        ai_agent.py              # Groq integration and tool definitions
        neon_service.py          # Neon PostgreSQL API client
    docker/
      runtimes/
        python/
          Dockerfile             # Base runtime image (python:3.12-slim)
          runner.py              # Wrapper that imports and calls handler()
    alembic/
      versions/                  # 9 migration files (001-009)
    requirements.txt             # Python dependencies
    .env.local                   # API keys (git-ignored)

  frontend/
    Dockerfile                   # Multi-stage build, served by nginx
    nginx.conf                   # SPA fallback, /api proxy, cache headers
    src/
      pages/
        Dashboard.tsx            # Overview stats
        Cluster.tsx              # Live worker fleet and placement policy
        Projects.tsx             # Project list
        ProjectDetail.tsx        # Project management (6 tabs)
        Functions.tsx            # Function list
        FunctionDetail.tsx       # Editor, test panel, version history, logs
        CreateProject.tsx        # New project form
        CreateFunction.tsx       # New function form
      components/                # ui/, layout/, functions/, projects/, chat/, auth/
      lib/api.ts                 # Typed API client with Clerk JWT injection

  infra/
    lb/nginx.conf                # Load balancer in front of the control plane
    terraform/                   # Production stack: ALB, Fargate, EC2 ASG, RDS, Redis
    terraform-single-node/       # One EC2 instance running docker-compose

  scripts/loadtest.py            # Concurrency load generator with a placement report
  docs/
    architecture.md              # How execution works and what maps to what in AWS
    thinking.md                  # Design decisions and the options rejected
  .github/workflows/ci.yml       # Tests, builds, migrations, terraform validate
```

## Setup Guide

Two ways to run it. Compose gives you the distributed system; the local install
gives you a fast edit-reload loop.

### Quick start (the whole cluster)

```bash
git clone https://github.com/islamborghini/clowdy.git
cd clowdy

# Optional: API keys. The stack starts without them, minus the AI
# assistant and managed databases.
cat > .env << 'EOF'
GROQ_API_KEY=gsk_your_key_here
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
NEON_API_KEY=your_neon_api_key_here
VITE_CLERK_PUBLISHABLE_KEY=pk_test_your_key_here
EOF

docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | The app |
| http://localhost:8080 | API, through the load balancer |
| http://localhost:8080/api/cluster | Live fleet state |
| http://localhost:8080/docs | OpenAPI docs |

Compose brings up Postgres, Redis, a one-shot migration job, two control-plane
replicas behind nginx, three workers, and the frontend. Scale the fleet while
it is running:

```bash
docker compose up -d --scale worker=6
```

New workers register themselves within one heartbeat and the scheduler starts
placing work on them. No restart, no config change.

### Prerequisites (local development)

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

The backend runs at http://localhost:8000. Interactive API docs at
http://localhost:8000/docs. Alembic migrations run automatically on startup.

With no `REDIS_URL` set there are no workers to dispatch to, so the control
plane executes functions in its own process against your local Docker daemon.
Everything works; `/api/cluster` reports `"mode": "single-node"`.

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
| `DEMO_MODE` | No | `false` | Read-only public demo: blocks writes, makes reads public |
| `FRONTEND_URL` | No | `http://localhost:5173` | -- |
| `GROQ_API_KEY` | Yes | -- | https://console.groq.com/keys |
| `CLERK_JWKS_URL` | Yes | -- | Clerk dashboard > API Keys |
| `NEON_API_KEY` | No | -- | https://console.neon.tech/account/api-keys |
| `REDIS_URL` | No | -- (single-node) | Enables the worker registry |
| `RUN_MIGRATIONS` | No | `true` | Set `false` on replicas; a migrate job owns the schema |
| `SQL_ECHO` | No | `false` | Log every SQL statement |

**Worker** (`backend/app/worker/main.py`):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `REDIS_URL` | Yes | -- | Where the worker publishes its heartbeat |
| `WORKER_ID` | No | hostname | Identity in the registry |
| `WORKER_URL` | No | auto-detected IP | Address the control plane dispatches to |
| `WORKER_PORT` | No | `9000` | Port advertised in the registry; must match uvicorn's |
| `WORKER_CONCURRENCY` | No | `8` | Max concurrent invocations before returning 429 |
| `WORKER_TTL_SECONDS` | No | `15` | How long a heartbeat stays valid |

**Frontend** (`frontend/.env.local`):

| Variable | Required | Default |
|---|---|---|
| `VITE_API_URL` | No | `http://localhost:8000` |
| `VITE_DEMO_MODE` | No | `false` | Hides write controls; cosmetic only, the backend enforces |

## Running the Cluster

```bash
docker compose up --build              # bring up the full topology
docker compose up -d --scale worker=6  # add workers, live
docker compose logs -f worker          # watch placement decisions
curl -s localhost:8080/api/cluster     # fleet state as JSON
```

Things worth trying, because they are the point of the architecture:

**Watch warm affinity.** Invoke one function repeatedly and watch
`/api/cluster`. Invocations concentrate on one worker and its warm container
count stays at 1, because the scheduler hashes on the image. Cold starts stop
after the first.

**Kill a worker.** `docker compose stop worker` (or kill one container).
Within 15 seconds its registry key expires and it disappears from
`/api/cluster`. In-flight requests aimed at it fail over to another node
immediately -- the dispatcher tries up to three workers before giving up.

**Saturate the fleet.** Deploy a function that sleeps, then
`python scripts/loadtest.py <id> --url http://localhost:8080 -n 200 -c 100`.
Once every worker is at its concurrency limit the API returns 503 with
`Retry-After` instead of queueing, and the load test reports the throttles.

**Kill a control-plane replica.** nginx takes it out of rotation after three
failures and requests keep succeeding on the other one.

## Deploying to AWS

Two Terraform stacks, both validated in CI.

**`infra/terraform-single-node/`** -- one EC2 instance running the same
`docker-compose.yml`, with a static IP and a systemd unit so it survives
reboots. About $15/month on a `t4g.small`, or free for twelve months on a
`t3.micro`. Still two control-plane replicas, three workers, and a real
scheduler between them; what it gives up is surviving the loss of the machine.

```bash
cd infra/terraform-single-node
terraform init
terraform apply -var="key_name=your-keypair" -var="allowed_ssh_cidr=$(curl -s ifconfig.me)/32"
```

**`infra/terraform/`** -- the production shape: ALB, ECS Fargate for the
control plane with CPU autoscaling, an EC2 auto scaling group for the worker
fleet, RDS Postgres, ElastiCache Redis, ECR with lifecycle policies, and
Secrets Manager. Roughly $110/month idle, most of it the ALB, NAT gateway, and
RDS.

```bash
cd infra/terraform
terraform init
export TF_VAR_db_password="$(openssl rand -base64 24)"
terraform plan
```

The control plane runs on Fargate and the workers run on EC2, and that split is
the deployment decision worth explaining: a worker's job is to create and exec
into containers, which needs a Docker daemon, and Fargate gives a task no
daemon, no socket, and no privileged mode. So the stateless half is serverless
and the half that runs serverless functions is not -- the same split AWS makes
for Lambda itself.

[docs/architecture.md](docs/architecture.md#local-topology-to-aws) maps every
compose service to its AWS counterpart and explains the security-group,
IAM, and health-check choices.

## Hosting a Public Demo

A public host runs Python from anyone who can reach it, so the demo deployment
is read-only. `DEMO_MODE=true` blocks every state-changing request at the API
edge, with two exceptions -- invoking a function and calling a gateway route,
which are the whole point of a deployed endpoint.

That check is one middleware rather than a guard on each of ~20 mutating
routes, because the failure mode of per-endpoint guards is not today's
oversight, it is the router added next month with no guard at all. Blocking by
HTTP method at the edge means a new route is locked down by default.
`/api/chat` is blocked too: the AI assistant has create, update, and delete
tools, so leaving it open would hand back everything demo mode closes.

Reads are public in demo mode -- every caller is a shared `demo` user -- so
visitors browse the seeded content instead of hitting 401s. Writes stay
blocked regardless of who is asking, so the two mechanisms are independent.

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose exec -T control-plane python -m app.seed_demo
```

The seeder is idempotent and creates four functions, each exercising a
different part of the platform: `hello` (minimal), `fibonacci` (real CPU work,
so the cold-then-warm difference is visible), `burn` (holds a slot, for
demonstrating backpressure), and `http_echo` (wired to gateway routes with
path params).

### Oracle Cloud Always Free

`infra/terraform-oracle/` deploys this to Oracle's Always Free tier: 4 ARM
cores, 24GB of memory, 200GB of disk, free permanently with no 12-month
cliff. The platform idles around 430MB, so nearly all of that is headroom for
function containers.

```bash
cd infra/terraform-oracle
terraform init
terraform apply    # needs tenancy/user OCIDs, API key fingerprint, SSH pubkey
```

Cloud-init installs Docker, clones the repo, brings up the demo overlay, and
seeds the example functions. Allow 5-10 minutes on first boot -- it builds
four images on an ARM box.

Two things that trip up a first Oracle deploy, both handled in the stack:

- The A1 ARM shape is heavily oversubscribed. `Out of host capacity` is a
  capacity error, not a config error; retry or pick a quieter region.
- Oracle's Ubuntu images ship an iptables policy that drops everything except
  SSH. Opening port 80 in the VCN security list is necessary but not
  sufficient, so cloud-init opens it on the host too and persists the rule.

## API Endpoints

### Health and Stats

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | No | Health check |
| GET | `/api/stats` | Yes | Dashboard statistics |
| GET | `/api/cluster` | No | Live worker fleet, load, and placement policy |

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
| GET | `/api/functions/:id` | Yes | Get a function (returns active version code) |
| PUT | `/api/functions/:id` | Yes | Update a function (new code creates a new version) |
| DELETE | `/api/functions/:id` | Yes | Delete a function |
| GET | `/api/functions/:id/versions` | Yes | List all versions, newest first |
| PUT | `/api/functions/:id/versions/:version` | Yes | Set a specific version as active (rollback) |

### Invocation

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/invoke/:id` | No | Invoke a function (503 when the fleet is saturated) |
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

Every function runs in a Docker container with strict limits:

- **Network off by default** -- `network_disabled=True` unless the function explicitly opts in via the per-function network toggle. The warm pool keys on this setting so a network-enabled function can never reuse a network-disabled container or vice versa.
- **Memory cap** -- 128MB limit prevents memory exhaustion
- **CPU cap** -- 0.5 cores prevents CPU monopolization
- **Timeout** -- 30 seconds maximum, container killed after
- **No volume mounts** -- code copied via `put_archive`, no host filesystem access
- **Warm pool reuse** -- containers are kept warm for fast invocations but capped in size (LRU eviction) and reaped after idle timeout. Code is copied in fresh on every invocation so versions cannot leak between calls.

### Demo Mode

When `DEMO_MODE=true`, one middleware rejects every `POST`/`PUT`/`PATCH`/
`DELETE` except `/api/invoke/*` and `/api/gateway/*`, so a public host cannot
have functions created or edited on it. The frontend flag only hides controls
that would fail; it is not the boundary, and the backend does not trust it.

### Fleet Isolation

- **Admission control** -- each worker refuses invocations past its concurrency
  limit with a 429, so one slow function cannot pull a host down
- **Backpressure** -- a saturated fleet returns 503 with `Retry-After` rather
  than queueing work it cannot run
- **Bounded retries** -- the dispatcher fails over across at most three workers,
  so a broken fleet sheds load instead of amplifying it
- **Enforced timeouts** -- the 30s limit is applied with `timeout --signal=KILL`
  inside the container, not around the Docker API call, so a hung function
  cannot pin a container forever
- **Least-privilege workers** (AWS) -- the worker instance profile grants ECR
  pull and SSM only, and IMDSv2 is required, because a worker running untrusted
  code is the blast radius of a container escape

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

## Testing

```bash
cd backend
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pytest
```

Coverage is deliberately narrow: the tests cover the logic where a
plausible-looking implementation is silently wrong.

| File | What it pins down |
|---|---|
| `test_scheduler.py` | Warm affinity is stable, different images spread, a hot worker is skipped, a full fleet returns no placement, removing a worker does not reshuffle the rest |
| `test_warm_pool.py` | Containers are reused, pool keys do not collide, LRU eviction destroys the right one, the reaper only takes idle containers |
| `test_gateway_matching.py` | Path params extract correctly, `:id` does not match across segments, exact methods beat `ANY` |

CI additionally applies every migration to an empty database and reverses them
all, builds all three images, runs a function end to end through the runtime
image, and validates both Terraform stacks.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run the backend (`./venv/bin/uvicorn app.main:app --reload`) and frontend (`npm run dev`) to verify
5. Commit and push
6. Open a pull request

### Code Style

- **No emojis** in code, comments, or commit messages
- Run `pytest` before opening a PR; CI runs it plus lint, build, and
  `terraform validate`
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
