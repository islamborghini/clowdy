# Clowdy

A simplified serverless function platform inspired by AWS Lambda. Write Python functions in a web editor, deploy them instantly, and get an HTTP endpoint to invoke them. Includes an AI assistant that can create and manage functions via natural language.

The motivation was to learn how does serverless cloud infrastructure work under the hood.

## How It Works

```
User writes Python code in the web editor
         |
         v
Code is saved to SQLite via FastAPI
         |
         v
POST /api/invoke/{id} triggers execution:
  1. Code is copied into a Docker container
  2. Container runs with resource limits (128MB RAM, 0.5 CPU, no network)
  3. Output is captured from stdout as JSON
  4. Container is destroyed after execution
         |
         v
Result + invocation log returned to the caller
```

## Features

- **Function CRUD** -- Create, edit, and delete Python functions through a Monaco code editor (same editor as VS Code)
- **Docker Execution** -- Functions run in isolated containers with memory limits, CPU limits, network disabled, and a 30-second timeout
- **HTTP Endpoints** -- Every function gets an invoke URL (`POST /api/invoke/{id}`) callable from anywhere
- **Invocation Logs** -- Every execution is logged with input, output, status, and duration
- **AI Agent** -- Chat panel powered by Groq (Llama) that can create, invoke, update, and delete functions via natural language using tool calling
- **Dashboard** -- Real-time stats: total functions, invocations, success rate, average duration

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, TypeScript, Tailwind CSS v4, shadcn/ui, React Router v7 |
| Backend | FastAPI (Python), SQLAlchemy 2.x async, SQLite (aiosqlite) |
| Execution | Docker containers (python:3.12-slim base image) |
| AI | Groq API with tool calling (Llama 4 Scout) |
| Code Editor | Monaco Editor (React) |

## Project Structure

```
clowdy/
  backend/
    app/
      main.py              # FastAPI app, health + stats endpoints
      config.py             # Environment variable settings
      database.py           # SQLAlchemy async engine + session
      models.py             # DB models (Function, Invocation)
      schemas.py            # Pydantic request/response schemas
      routers/
        functions.py        # CRUD endpoints for functions
        invoke.py           # Function execution + invocation logs
        chat.py             # AI agent chat endpoint
      services/
        docker_runner.py    # Docker container execution logic
        ai_agent.py         # Groq integration + tool definitions
    docker/
      runtimes/
        python/
          Dockerfile        # Python runtime base image
          runner.py          # Wrapper that calls handler(input)

  frontend/
    src/
      components/
        layout/             # Sidebar, Layout
        functions/           # FunctionCard, CodeEditor
        chat/               # ChatPanel, ChatMessage
      pages/                # Dashboard, Functions, CreateFunction, FunctionDetail
      lib/
        api.ts              # Typed API client
```

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (Docker Desktop, Colima, or similar)

### Backend

```bash
cd backend

# Create virtual environment and install dependencies
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install docker groq

# Build the Python runtime Docker image
cd docker/runtimes/python
docker build -t clowdy-python-runtime .
cd ../../..

# Set Groq API key (optional, for AI agent)
export GROQ_API_KEY="gsk_your_key_here"

# Start the server
./venv/bin/uvicorn app.main:app --reload
```

The backend runs at http://localhost:8000. API docs are at http://localhost:8000/docs.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The frontend runs at http://localhost:5173.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Dashboard statistics |
| POST | `/api/functions` | Create a function |
| GET | `/api/functions` | List all functions |
| GET | `/api/functions/:id` | Get a function |
| PUT | `/api/functions/:id` | Update a function |
| DELETE | `/api/functions/:id` | Delete a function |
| POST | `/api/invoke/:id` | Invoke a function |
| GET | `/api/functions/:id/invocations` | Get invocation logs |
| POST | `/api/chat` | Chat with AI agent |

## Example: Creating and Invoking a Function

```bash
# Create a function
curl -X POST http://localhost:8000/api/functions \
  -H "Content-Type: application/json" \
  -d '{"name": "greeter", "code": "def handler(input):\n    return {\"message\": f\"Hello, {input.get(chr(39)name, chr(39)World)}!\"}"}'

# Invoke it (use the ID from the response above)
curl -X POST http://localhost:8000/api/invoke/FUNCTION_ID \
  -H "Content-Type: application/json" \
  -d '{"input": {"name": "Islam"}}'

# Response: {"success": true, "output": {"message": "Hello, Islam!"}, "duration_ms": 350}
```

## Security Model

User code is untrusted. Docker provides isolation:

- **No network access** -- `network_disabled=True` prevents outbound requests
- **Memory cap** -- 128MB limit prevents memory bombs
- **CPU cap** -- 0.5 cores prevents CPU hogging
- **Timeout** -- 30-second maximum execution time
- **No volume mounts** -- Code is copied in via `put_archive`, not mounted from host
- **Ephemeral containers** -- Destroyed after every execution
