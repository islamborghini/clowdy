/**
 * Function Detail page.
 *
 * Shows a single function's code, configuration, and invocation logs.
 * The function ID comes from the URL parameter (e.g. /functions/abc123).
 * Currently a placeholder - Phase 2 will fetch and display real data.
 */
import { useParams, Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function FunctionDetail() {
  // useParams() extracts URL parameters defined in the route.
  // Our route is "/functions/:id", so useParams() gives us { id: "abc123" }.
  const { id } = useParams()

  return (
    <div>
      <div className="mb-6 flex items-center gap-4">
        <Link to="/functions">
          <Button variant="ghost" size="sm">
            ← Back
          </Button>
        </Link>
        <h2 className="text-3xl font-bold">Function: {id}</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Function Details</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Function details, code, and logs will go here (Phase 2)
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
