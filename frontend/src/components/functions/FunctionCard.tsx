/**
 * Card component for displaying a single function in the functions list.
 *
 * Shows the function name, description, runtime badge, status badge,
 * and timestamps. The entire card is clickable and navigates to the
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
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate text-lg">{fn.name}</CardTitle>
          </div>
          <div className="ml-2 flex gap-1.5">
            <Badge variant="outline" className="text-xs">
              {fn.runtime}
            </Badge>
            <Badge variant={fn.status === "active" ? "default" : "destructive"}>
              {fn.status}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {fn.description && (
            <p className="mb-3 line-clamp-2 text-sm text-muted-foreground">
              {fn.description}
            </p>
          )}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Created {new Date(fn.created_at).toLocaleDateString()}</span>
            <span>Updated {new Date(fn.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
