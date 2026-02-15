/**
 * Create Function page.
 *
 * Provides a form with name, description, and a Monaco code editor
 * for writing the function's source code. On submit, it calls the
 * backend API to create the function, then redirects to its detail page.
 */
import { useState } from "react"
import { Link, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CodeEditor } from "@/components/functions/CodeEditor"
import { api } from "@/lib/api"

// Default code template so users aren't staring at a blank editor
const DEFAULT_CODE = `def handler(input):
    """
    This is your serverless function.

    Args:
        input: A dictionary containing the JSON data sent to your function.

    Returns:
        A dictionary that will be sent back as JSON to the caller.
    """
    name = input.get("name", "World")
    return {"message": f"Hello, {name}!"}
`

export function CreateFunction() {
  const navigate = useNavigate()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [code, setCode] = useState(DEFAULT_CODE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleDeploy() {
    // Basic validation
    if (!name.trim()) {
      setError("Function name is required")
      return
    }
    if (!code.trim()) {
      setError("Function code is required")
      return
    }

    setLoading(true)
    setError("")

    try {
      const fn = await api.functions.create({
        name: name.trim(),
        description: description.trim(),
        code,
      })
      // Redirect to the newly created function's detail page
      navigate(`/functions/${fn.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create function")
    } finally {
      setLoading(false)
    }
  }

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

      <div className="space-y-6">
        {/* Name and description inputs */}
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Function Name</Label>
              <Input
                id="name"
                placeholder="e.g. celsius_converter"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                placeholder="What does this function do?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        {/* Code editor */}
        <Card>
          <CardHeader>
            <CardTitle>Code</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-md border">
              <CodeEditor value={code} onChange={setCode} />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Your function must define a handler(input) function that accepts a
              dictionary and returns a dictionary.
            </p>
          </CardContent>
        </Card>

        {/* Error message and deploy button */}
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        <Button onClick={handleDeploy} disabled={loading} size="lg">
          {loading ? "Deploying..." : "Deploy Function"}
        </Button>
      </div>
    </div>
  )
}
