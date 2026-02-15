/**
 * API client for communicating with the FastAPI backend.
 *
 * This module provides a typed wrapper around the browser's fetch API.
 * All requests go to the backend server (default: http://localhost:8000).
 * You can override the URL by setting VITE_API_URL in a .env file.
 *
 * Authentication: The Clerk JWT token is automatically included in the
 * Authorization header via the auth.ts token provider.
 */

import { getAuthToken } from "./auth"

// Read the backend URL from environment variables, falling back to localhost.
// "import.meta.env" is Vite's way of accessing env vars (similar to process.env in Node).
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

/**
 * Generic fetch wrapper that handles JSON requests/responses and errors.
 *
 * Automatically includes the Clerk JWT token in the Authorization header
 * if the user is signed in.
 *
 * @param path - The API endpoint path (e.g. "/api/functions")
 * @param options - Standard fetch options (method, body, headers, etc.)
 * @returns The parsed JSON response, typed as T
 * @throws Error if the response status is not 2xx
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = await getAuthToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${API_URL}${path}`, {
    headers: { ...headers, ...(options?.headers as Record<string, string>) },
    ...options,
  })

  // If the response is not OK (status 400, 404, 500, etc.), throw an error.
  // We try to parse the error body as JSON (FastAPI returns { "detail": "..." }),
  // but fall back to the HTTP status text if parsing fails.
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || "API request failed")
  }

  return res.json()
}

/**
 * Organized API methods grouped by resource.
 *
 * Usage:
 *   api.health()                          - Check if backend is running
 *   api.functions.list()                  - Get all functions
 *   api.functions.create({ name, code })  - Create a new function
 *   api.functions.get("abc123")           - Get a specific function
 *   api.functions.update("abc123", {...}) - Update a function
 *   api.functions.delete("abc123")        - Delete a function
 *   api.functions.invoke("abc123", {...}) - Invoke a function
 *   api.functions.invocations("abc123")   - Get invocation logs
 *   api.chat([...messages])              - Chat with the AI agent
 */
export const api = {
  /** Ping the backend to check if it's running. Returns { status: "ok" }. */
  health: () => apiFetch<{ status: string }>("/api/health"),

  /** Fetch dashboard statistics (function count, invocation count, etc.). */
  stats: () => apiFetch<StatsResponse>("/api/stats"),

  /**
   * Send a message to the AI agent. Pass the full conversation history
   * so the AI has context of previous messages.
   */
  chat: (messages: ChatMessage[]) =>
    apiFetch<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),

  projects: {
    list: () => apiFetch<ProjectResponse[]>("/api/projects"),

    get: (id: string) => apiFetch<ProjectResponse>(`/api/projects/${id}`),

    create: (data: ProjectCreate) =>
      apiFetch<ProjectResponse>("/api/projects", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    update: (id: string, data: Partial<ProjectCreate>) =>
      apiFetch<ProjectResponse>(`/api/projects/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    delete: (id: string) =>
      apiFetch<{ detail: string }>(`/api/projects/${id}`, {
        method: "DELETE",
      }),

    functions: (id: string) =>
      apiFetch<FunctionResponse[]>(`/api/projects/${id}/functions`),

    envVars: {
      list: (projectId: string) =>
        apiFetch<EnvVarResponse[]>(`/api/projects/${projectId}/env`),

      set: (projectId: string, data: EnvVarSet) =>
        apiFetch<EnvVarResponse>(`/api/projects/${projectId}/env`, {
          method: "POST",
          body: JSON.stringify(data),
        }),

      delete: (projectId: string, key: string) =>
        apiFetch<{ detail: string }>(`/api/projects/${projectId}/env/${key}`, {
          method: "DELETE",
        }),
    },

    routes: {
      list: (projectId: string) =>
        apiFetch<RouteResponse[]>(`/api/projects/${projectId}/routes`),

      create: (projectId: string, data: RouteCreate) =>
        apiFetch<RouteResponse>(`/api/projects/${projectId}/routes`, {
          method: "POST",
          body: JSON.stringify(data),
        }),

      update: (projectId: string, routeId: string, data: RouteUpdate) =>
        apiFetch<RouteResponse>(
          `/api/projects/${projectId}/routes/${routeId}`,
          {
            method: "PUT",
            body: JSON.stringify(data),
          }
        ),

      delete: (projectId: string, routeId: string) =>
        apiFetch<{ detail: string }>(
          `/api/projects/${projectId}/routes/${routeId}`,
          {
            method: "DELETE",
          }
        ),
    },
  },

  functions: {
    /** Fetch all functions for the current user, newest first. */
    list: () => apiFetch<FunctionResponse[]>("/api/functions"),

    /** Fetch a single function by its ID. */
    get: (id: string) => apiFetch<FunctionResponse>(`/api/functions/${id}`),

    /** Create a new function. Returns the created function with its generated ID. */
    create: (data: FunctionCreate) =>
      apiFetch<FunctionResponse>("/api/functions", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    /**
     * Update an existing function. Only the fields you include will be changed.
     * Partial<FunctionCreate> means all fields are optional.
     */
    update: (id: string, data: Partial<FunctionCreate>) =>
      apiFetch<FunctionResponse>(`/api/functions/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    /** Delete a function by ID. Returns { detail: "Function deleted" }. */
    delete: (id: string) =>
      apiFetch<{ detail: string }>(`/api/functions/${id}`, {
        method: "DELETE",
      }),

    /**
     * Invoke (run) a function with the given input data.
     * This sends the code to a Docker container and returns the result.
     */
    invoke: (id: string, input: Record<string, unknown> = {}) =>
      apiFetch<InvokeResponse>(`/api/invoke/${id}`, {
        method: "POST",
        body: JSON.stringify({ input }),
      }),

    /** Fetch invocation logs for a function, newest first. */
    invocations: (id: string) =>
      apiFetch<InvocationResponse[]>(`/api/functions/${id}/invocations`),
  },
}

// ----- Types -----
// These interfaces mirror the Pydantic schemas on the backend (backend/app/schemas.py).
// Keeping them in sync ensures the frontend and backend agree on data shapes.

/** What the backend returns when you fetch a project. */
export interface ProjectResponse {
  id: string
  name: string
  slug: string
  description: string
  status: string
  function_count: number
  created_at: string
  updated_at: string
}

/** What the backend expects when you create a new project. */
export interface ProjectCreate {
  name: string
  description?: string
}

/** What the backend returns when you fetch a function. */
export interface FunctionResponse {
  id: string
  name: string
  description: string
  code: string
  runtime: string
  status: string
  created_at: string
  updated_at: string
}

/** What the backend returns when you fetch an env var. */
export interface EnvVarResponse {
  id: string
  key: string
  value: string
  is_secret: boolean
  created_at: string
  updated_at: string
}

/** What the backend expects when you set an env var. */
export interface EnvVarSet {
  key: string
  value: string
  is_secret?: boolean
}

/** What the backend returns when you fetch a route. */
export interface RouteResponse {
  id: string
  project_id: string
  function_id: string
  method: string
  path: string
  description: string
  created_at: string
  updated_at: string
}

/** What the backend expects when you create a new route. */
export interface RouteCreate {
  function_id: string
  method: string
  path: string
  description?: string
}

/** What the backend expects when you update a route. */
export interface RouteUpdate {
  function_id?: string
  method?: string
  path?: string
  description?: string
}

/** What the backend expects when you create a new function. */
export interface FunctionCreate {
  name: string
  description?: string
  code: string
  runtime?: string // defaults to "python" on the backend
  project_id?: string
}

/** What the backend returns when you invoke a function. */
export interface InvokeResponse {
  success: boolean
  output?: Record<string, unknown>
  error?: string
  duration_ms: number
  invocation_id: string
}

/** A single invocation log entry returned by the backend. */
export interface InvocationResponse {
  id: string
  function_id: string
  input: string
  output: string
  status: string
  duration_ms: number
  source: string
  http_method: string | null
  http_path: string | null
  created_at: string
}

// --- Stats types ---

/** Dashboard statistics returned by the backend. */
export interface StatsResponse {
  total_functions: number
  total_invocations: number
  success_rate: number
  avg_duration_ms: number
}

// --- Chat types ---

/** A single message in the chat conversation. */
export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

/** What the backend returns from the AI chat endpoint. */
export interface ChatResponse {
  response: string
  tool_calls: Array<{
    tool: string
    args: Record<string, unknown>
    result: Record<string, unknown>
  }>
}
