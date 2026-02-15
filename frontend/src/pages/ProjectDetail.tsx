/**
 * Project Detail page.
 *
 * Shows project metadata and a tabbed interface. Currently the "Functions"
 * tab is active; Routes, Env Vars, Database, and Settings tabs will be
 * added in later phases.
 */
import { useEffect, useState } from "react"
import { useParams, Link, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { FunctionCard } from "@/components/functions/FunctionCard"
import {
  api,
  type ProjectResponse,
  type FunctionResponse,
} from "@/lib/api"

type Tab = "functions" | "settings"

export function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [project, setProject] = useState<ProjectResponse | null>(null)
  const [functions, setFunctions] = useState<FunctionResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [activeTab, setActiveTab] = useState<Tab>("functions")
  const [deleting, setDeleting] = useState(false)

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

  if (loading) return <p className="text-muted-foreground">Loading...</p>
  if (error) return <p className="text-destructive">{error}</p>
  if (!project) return <p className="text-muted-foreground">Project not found</p>

  const tabs: { key: Tab; label: string }[] = [
    { key: "functions", label: "Functions" },
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
