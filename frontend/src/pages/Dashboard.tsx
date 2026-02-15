/**
 * Dashboard page - the home screen of Clowdy.
 *
 * Shows overview stats fetched from GET /api/stats: backend connection
 * status, total functions, total invocations, success rate, and average
 * execution duration. All numbers are real data from the database.
 */
import { useEffect, useState } from "react"
import { Link } from "react-router"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ProjectCard } from "@/components/projects/ProjectCard"
import { api, type StatsResponse, type ProjectResponse } from "@/lib/api"

export function Dashboard() {
  const [backendStatus, setBackendStatus] = useState<string>("checking...")
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [recentProjects, setRecentProjects] = useState<ProjectResponse[]>([])

  useEffect(() => {
    api
      .health()
      .then(() => setBackendStatus("connected"))
      .catch(() => setBackendStatus("offline"))

    api
      .stats()
      .then(setStats)
      .catch(() => {})

    api.projects
      .list()
      .then((projects) => setRecentProjects(projects.slice(0, 3)))
      .catch(() => {})
  }, [])

  return (
    <div>
      <h2 className="mb-6 text-3xl font-bold">Dashboard</h2>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Backend Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-bold">
              {backendStatus === "connected"
                ? "Connected"
                : backendStatus === "offline"
                  ? "Offline"
                  : "Checking..."}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Functions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {stats?.total_functions ?? "-"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Invocations
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {stats?.total_invocations ?? "-"}
            </p>
            {stats && stats.total_invocations > 0 && (
              <p className="mt-1 text-sm text-muted-foreground">
                {stats.success_rate}% success rate
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Avg Duration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {stats && stats.total_invocations > 0
                ? `${stats.avg_duration_ms}ms`
                : "-"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Projects */}
      {recentProjects.length > 0 && (
        <div className="mt-8">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Recent Projects</h3>
            <Link to="/projects" className="text-sm text-muted-foreground hover:text-foreground">
              View all
            </Link>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {recentProjects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
