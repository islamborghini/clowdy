/**
 * Functions list page.
 *
 * Displays all deployed serverless functions. Currently shows an empty state
 * placeholder - will be replaced with actual function cards fetched from
 * the backend API in Phase 2.
 */
import { Link } from "react-router"
import { Button } from "@/components/ui/button"

export function Functions() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-3xl font-bold">Functions</h2>
        {/* Link navigates without a full page reload (client-side routing) */}
        <Link to="/functions/new">
          <Button>+ New Function</Button>
        </Link>
      </div>

      {/* Empty state - shown when the user has no functions yet.
          Will be replaced with a list of FunctionCard components in Phase 2. */}
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <p className="text-lg text-muted-foreground">No functions yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Create your first serverless function to get started
        </p>
      </div>
    </div>
  )
}
