/**
 * Card component for displaying a single project in the projects list.
 *
 * Shows the project name, description, function count, status,
 * and timestamps. The entire card is clickable and navigates to
 * the project's detail page.
 */
import { Link } from "react-router"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { ProjectResponse } from "@/lib/api"

interface ProjectCardProps {
  project: ProjectResponse
}

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Link to={`/projects/${project.id}`}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardHeader className="flex flex-row items-start justify-between pb-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate text-lg">{project.name}</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              /{project.slug}
            </p>
          </div>
          <Badge variant={project.status === "active" ? "default" : "secondary"}>
            {project.status}
          </Badge>
        </CardHeader>
        <CardContent>
          {project.description && (
            <p className="mb-3 line-clamp-2 text-sm text-muted-foreground">
              {project.description}
            </p>
          )}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>
              {project.function_count} {project.function_count === 1 ? "function" : "functions"}
            </span>
            <span>Created {new Date(project.created_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
