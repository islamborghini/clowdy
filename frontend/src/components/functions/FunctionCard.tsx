/**
 * Card component for displaying a single function in the functions list.
 *
 * Shows the function name, description, runtime, status badge, and
 * creation date. The entire card is clickable and navigates to the
 * function's detail page.
 */
import { Link } from "react-router"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { FunctionResponse } from "@/lib/api"

interface FunctionCardProps {
  fn: FunctionResponse
}

export function FunctionCard({ fn }: FunctionCardProps) {
  return (
    <Link to={`/functions/${fn.id}`}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardHeader className="flex flex-row items-start justify-between pb-2">
          <CardTitle className="text-lg">{fn.name}</CardTitle>
          <Badge variant={fn.status === "active" ? "default" : "destructive"}>
            {fn.status}
          </Badge>
        </CardHeader>
        <CardContent>
          {fn.description && (
            <p className="mb-2 text-sm text-muted-foreground">
              {fn.description}
            </p>
          )}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Runtime: {fn.runtime}</span>
            <span>Created: {new Date(fn.created_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
