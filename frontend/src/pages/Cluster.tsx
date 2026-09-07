/**
 * Cluster page - live view of the worker fleet.
 *
 * Polls GET /api/cluster and renders what the scheduler is actually working
 * with: which nodes are alive, how loaded each one is, how many warm
 * containers it is holding, and how invocations have distributed across them.
 *
 * Run scripts/loadtest.py with this page open and the placement bars move.
 */
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { api, type ClusterResponse } from "@/lib/api"

const POLL_INTERVAL_MS = 2000

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`
}

export function Cluster() {
  const [cluster, setCluster] = useState<ClusterResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = () => {
      api
        .cluster()
        .then((data) => {
          if (cancelled) return
          setCluster(data)
          setError(null)
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message)
        })
    }

    poll()
    const timer = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  // Busiest worker sets the bar scale, so the chart shows relative load rather
  // than a row of near-empty bars.
  const busiest = Math.max(1, ...(cluster?.workers ?? []).map((w) => w.invocations_total))

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold">Cluster</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Live worker fleet, refreshed every {POLL_INTERVAL_MS / 1000}s
          </p>
        </div>
        {cluster && (
          <Badge variant={cluster.mode === "distributed" ? "default" : "secondary"}>
            {cluster.mode}
          </Badge>
        )}
      </div>

      {error && (
        <Card className="mb-6 border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      <div className="mb-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Workers Online
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{cluster?.workers.length ?? "-"}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Fleet Capacity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {cluster
                ? `${cluster.workers.reduce((n, w) => n + w.inflight, 0)} / ${cluster.workers.reduce((n, w) => n + w.capacity, 0)}`
                : "-"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">in flight now</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Warm Containers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {cluster?.workers.reduce((n, w) => n + w.warm_containers, 0) ?? "-"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">pooled across the fleet</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Warm Hit Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{cluster ? `${cluster.totals.warm_rate}%` : "-"}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {cluster?.totals.cold_starts ?? 0} cold of {cluster?.totals.invocations ?? 0}
            </p>
          </CardContent>
        </Card>
      </div>

      {cluster?.mode === "single-node" && (
        <Card className="mb-6">
          <CardContent className="pt-6 text-sm text-muted-foreground">
            No workers are registered, so the control plane is executing functions
            in its own process. Start the fleet with{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
              docker compose up --build
            </code>{" "}
            to distribute them.
          </CardContent>
        </Card>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Nodes</CardTitle>
        </CardHeader>
        <CardContent>
          {!cluster?.workers.length ? (
            <p className="text-sm text-muted-foreground">No workers registered.</p>
          ) : (
            <div className="space-y-4">
              {cluster.workers.map((worker) => (
                <div key={worker.id} className="rounded-lg border p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <p className="font-mono text-sm font-medium">{worker.id}</p>
                      <p className="text-xs text-muted-foreground">{worker.url}</p>
                    </div>
                    <div className="text-right text-xs text-muted-foreground">
                      <p>up {formatUptime(worker.uptime_seconds)}</p>
                      <p>
                        {worker.warm_containers} warm - {worker.cold_starts_since_start} cold
                        starts
                      </p>
                    </div>
                  </div>

                  {/* Concurrency in use, the number the scheduler balances on */}
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                      <span>
                        {worker.inflight} / {worker.capacity} concurrent
                      </span>
                      <span>{worker.load}%</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${Math.min(100, worker.load)}%` }}
                      />
                    </div>
                  </div>

                  {/* Lifetime share of invocations, from the durable log */}
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                      <span>{worker.invocations_total} invocations placed here</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-muted-foreground/50 transition-all"
                        style={{ width: `${(worker.invocations_total / busiest) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Placement Policy</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-muted-foreground">
            Invocations are placed by consistent hashing with bounded loads. The hash key
            is the container image plus its network setting, so repeat calls land on the
            worker already holding a warm container for them. When that worker is carrying
            more than its fair share, the ring walks past it.
          </p>
          {cluster && (
            <dl className="grid gap-x-6 gap-y-1 pt-2 sm:grid-cols-2">
              {[
                ["Algorithm", cluster.policy.algorithm],
                ["Affinity key", cluster.policy.affinity_key],
                ["Virtual nodes per worker", cluster.policy.virtual_nodes],
                ["Balance factor", cluster.policy.balance_factor],
                ["Shared registry", cluster.redis_enabled ? "Redis" : "disabled"],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between border-b py-1">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-mono text-xs">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
