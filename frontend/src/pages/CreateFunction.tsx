import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function CreateFunction() {
  return (
    <div>
      <div className="mb-6 flex items-center gap-4">
        <Link to="/functions">
          <Button variant="ghost" size="sm">
            ← Back
          </Button>
        </Link>
        <h2 className="text-3xl font-bold">New Function</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Create Function</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Code editor will go here (Monaco Editor - Phase 2)
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
