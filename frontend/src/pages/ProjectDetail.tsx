/**
 * Project Detail page.
 *
 * Shows project metadata and a tabbed interface with Functions,
 * Environment Variables, and Settings tabs.
 */
import { useEffect, useState } from "react"
import { useParams, Link, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { FunctionCard } from "@/components/functions/FunctionCard"
import {
  api,
  type ProjectResponse,
  type FunctionResponse,
  type EnvVarResponse,
} from "@/lib/api"

type Tab = "functions" | "environment" | "settings"

export function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [project, setProject] = useState<ProjectResponse | null>(null)
  const [functions, setFunctions] = useState<FunctionResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [activeTab, setActiveTab] = useState<Tab>("functions")
  const [deleting, setDeleting] = useState(false)

  // Env vars state
  const [envVars, setEnvVars] = useState<EnvVarResponse[]>([])
  const [envLoading, setEnvLoading] = useState(false)
  const [envError, setEnvError] = useState("")
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")
  const [newIsSecret, setNewIsSecret] = useState(true)
  const [savingEnv, setSavingEnv] = useState(false)
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!id) return
    Promise.all([api.projects.get(id), api.projects.functions(id)])
      .then(([proj, fns]) => {
        setProject(proj)
        setFunctions(fns)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [id])

  // Load env vars when the environment tab is activated
  useEffect(() => {
    if (activeTab !== "environment" || !id) return
    setEnvLoading(true)
    api.projects.envVars
      .list(id)
      .then(setEnvVars)
      .catch((err) => setEnvError(err.message))
      .finally(() => setEnvLoading(false))
  }, [activeTab, id])

  async function handleDelete() {
    if (!id || !project) return
    if (!window.confirm(`Delete project "${project.name}" and all its functions?`))
      return

    setDeleting(true)
    try {
      await api.projects.delete(id)
      navigate("/projects")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete")
      setDeleting(false)
    }
  }

  async function handleAddEnvVar() {
    if (!id || !newKey.trim()) return
    setSavingEnv(true)
    setEnvError("")
    try {
      const created = await api.projects.envVars.set(id, {
        key: newKey.trim(),
        value: newValue,
        is_secret: newIsSecret,
      })
      // Replace if exists (upsert), otherwise add
      setEnvVars((prev) => {
        const filtered = prev.filter((ev) => ev.key !== created.key)
        return [...filtered, created].sort((a, b) => a.key.localeCompare(b.key))
      })
      setNewKey("")
      setNewValue("")
      setNewIsSecret(true)
    } catch (err) {
      setEnvError(err instanceof Error ? err.message : "Failed to save env var")
    } finally {
      setSavingEnv(false)
    }
  }

  async function handleDeleteEnvVar(key: string) {
    if (!id) return
    if (!window.confirm(`Delete environment variable "${key}"?`)) return
    try {
      await api.projects.envVars.delete(id, key)
      setEnvVars((prev) => prev.filter((ev) => ev.key !== key))
    } catch (err) {
      setEnvError(err instanceof Error ? err.message : "Failed to delete env var")
    }
  }

  function toggleReveal(key: string) {
    setRevealedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  if (loading) return <p className="text-muted-foreground">Loading...</p>
  if (error) return <p className="text-destructive">{error}</p>
  if (!project) return <p className="text-muted-foreground">Project not found</p>

  const tabs: { key: Tab; label: string }[] = [
    { key: "functions", label: "Functions" },
    { key: "environment", label: "Environment" },
    { key: "settings", label: "Settings" },
  ]

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/projects">
            <Button variant="ghost" size="sm">
              &larr; Back
            </Button>
          </Link>
          <div>
            <h2 className="text-3xl font-bold">{project.name}</h2>
            <p className="text-sm text-muted-foreground">/{project.slug}</p>
          </div>
          <Badge variant={project.status === "active" ? "default" : "secondary"}>
            {project.status}
          </Badge>
        </div>
      </div>

      {project.description && (
        <p className="mb-6 text-muted-foreground">{project.description}</p>
      )}

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "functions" && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">
              Functions ({functions.length})
            </h3>
            <Link to={`/projects/${id}/functions/new`}>
              <Button size="sm">+ Add Function</Button>
            </Link>
          </div>

          {functions.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
              <p className="text-muted-foreground">
                No functions in this project yet
              </p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {functions.map((fn) => (
                <FunctionCard key={fn.id} fn={fn} />
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "environment" && (
        <div className="space-y-6">
          {/* Add env var form */}
          <Card>
            <CardHeader>
              <CardTitle>Add Variable</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
                <div className="flex-1 space-y-2">
                  <Label htmlFor="env-key">Key</Label>
                  <Input
                    id="env-key"
                    placeholder="e.g. API_KEY"
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value)}
                  />
                </div>
                <div className="flex-1 space-y-2">
                  <Label htmlFor="env-value">Value</Label>
                  <Input
                    id="env-value"
                    placeholder="e.g. sk-abc123"
                    type={newIsSecret ? "password" : "text"}
                    value={newValue}
                    onChange={(e) => setNewValue(e.target.value)}
                  />
                </div>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={newIsSecret}
                      onChange={(e) => setNewIsSecret(e.target.checked)}
                    />
                    Secret
                  </label>
                  <Button onClick={handleAddEnvVar} disabled={savingEnv || !newKey.trim()}>
                    {savingEnv ? "Saving..." : "Add"}
                  </Button>
                </div>
              </div>
              {envError && (
                <p className="mt-2 text-sm text-destructive">{envError}</p>
              )}
            </CardContent>
          </Card>

          {/* Env vars table */}
          <Card>
            <CardHeader>
              <CardTitle>Variables ({envVars.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {envLoading ? (
                <p className="text-muted-foreground">Loading...</p>
              ) : envVars.length === 0 ? (
                <p className="text-muted-foreground">
                  No environment variables set. Variables you add here will be
                  available to all functions in this project via os.environ.
                </p>
              ) : (
                <div className="space-y-2">
                  {envVars.map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-center gap-3 rounded-md border px-4 py-3"
                    >
                      <code className="min-w-35 font-mono text-sm font-semibold">
                        {ev.key}
                      </code>
                      <span className="flex-1 truncate font-mono text-sm text-muted-foreground">
                        {ev.is_secret && !revealedKeys.has(ev.key)
                          ? "********"
                          : ev.value}
                      </span>
                      <div className="flex items-center gap-2">
                        {ev.is_secret && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleReveal(ev.key)}
                          >
                            {revealedKeys.has(ev.key) ? "Hide" : "Reveal"}
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => handleDeleteEnvVar(ev.key)}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "settings" && (
        <Card>
          <CardHeader>
            <CardTitle>Danger Zone</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Deleting a project will permanently remove it and all its
              functions. This action cannot be undone.
            </p>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Deleting..." : "Delete Project"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
