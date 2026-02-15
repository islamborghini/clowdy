import { Link } from "react-router"
import { Button } from "@/components/ui/button"

export function Functions() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-3xl font-bold">Functions</h2>
        <Link to="/functions/new">
          <Button>+ New Function</Button>
        </Link>
      </div>

      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <p className="text-lg text-muted-foreground">No functions yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Create your first serverless function to get started
        </p>
      </div>
    </div>
  )
}
