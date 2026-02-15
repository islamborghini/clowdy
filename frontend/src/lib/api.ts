const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || "API request failed")
  }

  return res.json()
}

export const api = {
  health: () => apiFetch<{ status: string }>("/api/health"),
  functions: {
    list: () => apiFetch<FunctionResponse[]>("/api/functions"),
    get: (id: string) => apiFetch<FunctionResponse>(`/api/functions/${id}`),
    create: (data: FunctionCreate) =>
      apiFetch<FunctionResponse>("/api/functions", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<FunctionCreate>) =>
      apiFetch<FunctionResponse>(`/api/functions/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiFetch<{ detail: string }>(`/api/functions/${id}`, {
        method: "DELETE",
      }),
  },
}

// Types matching the backend schemas
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

export interface FunctionCreate {
  name: string
  description?: string
  code: string
  runtime?: string
}
