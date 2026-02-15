/**
 * Dashboard page - the home screen of Clowdy.
 *
 * Shows overview stats: backend connection status, total functions count,
 * and total invocations. On mount, it pings the backend health endpoint
 * and fetches the function list to display live data.
 */
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"

export function Dashboard() {
  const [backendStatus, setBackendStatus] = useState<string>("checking...")
  const [functionCount, setFunctionCount] = useState(0)

  // useEffect with [] runs once when the component first renders (on mount).
  // We use it to fetch initial data from the backend.
  useEffect(() => {
    // Check if the backend is running by calling the health endpoint
    api
      .health()
      .then(() => setBackendStatus("connected"))
      .catch(() => setBackendStatus("offline"))

    // Fetch all functions to show the count
    api.functions
      .list()
      .then((fns) => setFunctionCount(fns.length))
      .catch(() => {})
  }, [])

  return (
    <div>
      <h2 className="mb-6 text-3xl font-bold">Dashboard</h2>

      {/* Stats cards in a responsive 3-column grid */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Backend Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-bold">
              {backendStatus === "connected" ? "Connected" : backendStatus === "offline" ? "Offline" : "Checking..."}
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
            <p className="text-3xl font-bold">{functionCount}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Invocations
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
