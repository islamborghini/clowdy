/**
 * Projects list page.
 *
 * Fetches all projects from the backend API and displays them
 * as clickable cards. Shows an empty state when no projects exist yet.
 */
import { useEffect, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { ProjectCard } from "@/components/projects/ProjectCard"
import { api, type ProjectResponse } from "@/lib/api"

export function Projects() {
  const [projects, setProjects] = useState<ProjectResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.projects
      .list()
      .then(setProjects)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-3xl font-bold">Projects</h2>
        <Link to="/projects/new">
          <Button>+ New Project</Button>
        </Link>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <p className="text-lg text-muted-foreground">No projects yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create a project to group your functions together
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  )
}
