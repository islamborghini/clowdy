/**
 * Functions list page.
 *
 * Fetches all deployed functions from the backend API and displays them
 * as clickable cards. Shows an empty state when no functions exist yet.
 */
import { useEffect, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { FunctionCard } from "@/components/functions/FunctionCard"
import { api, type FunctionResponse } from "@/lib/api"

export function Functions() {
  const [functions, setFunctions] = useState<FunctionResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.functions
      .list()
      .then(setFunctions)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-3xl font-bold">Functions</h2>
        <Link to="/functions/new">
          <Button>+ New Function</Button>
        </Link>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : functions.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <p className="text-lg text-muted-foreground">No functions yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first serverless function to get started
          </p>
        </div>
      ) : (
        /* Function cards grid */
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {functions.map((fn) => (
            <FunctionCard key={fn.id} fn={fn} />
          ))}
        </div>
      )}
    </div>
  )
}
