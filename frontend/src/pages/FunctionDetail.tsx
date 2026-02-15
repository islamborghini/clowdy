import { useParams, Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function FunctionDetail() {
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
