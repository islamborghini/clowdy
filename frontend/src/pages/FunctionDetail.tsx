/**
 * Function Detail page.
 *
 * Displays a single function's metadata, source code (in a Monaco editor),
 * and its invoke URL. Supports editing the code and deleting the function.
 *
 * The function ID comes from the URL parameter (e.g. /functions/abc123).
 */
import { useEffect, useState } from "react"
import { useParams, Link, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CodeEditor } from "@/components/functions/CodeEditor"
import { api, type FunctionResponse } from "@/lib/api"

export function FunctionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [fn, setFn] = useState<FunctionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // Edit mode state
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editCode, setEditCode] = useState("")
  const [saving, setSaving] = useState(false)

  // The URL users will call to invoke this function (won't work until Step 3)
  const invokeUrl = `http://localhost:8000/api/invoke/${id}`

  // Fetch function data on mount
  useEffect(() => {
    if (!id) return
    api.functions
      .get(id)
      .then((data) => {
        setFn(data)
        setEditName(data.name)
        setEditDescription(data.description)
        setEditCode(data.code)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [id])

  /** Enter edit mode - populate form fields with current values. */
  function startEditing() {
    if (!fn) return
    setEditName(fn.name)
    setEditDescription(fn.description)
    setEditCode(fn.code)
    setEditing(true)
  }

  /** Save edited function to the backend. */
  async function handleSave() {
    if (!id) return
    setSaving(true)
    try {
      const updated = await api.functions.update(id, {
        name: editName,
        description: editDescription,
        code: editCode,
      })
      setFn(updated)
      setEditing(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  /** Delete the function after confirmation. */
  async function handleDelete() {
    if (!id) return
    if (!window.confirm("Are you sure you want to delete this function?")) return

    try {
      await api.functions.delete(id)
      navigate("/functions")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete")
    }
  }

  if (loading) return <p className="text-muted-foreground">Loading...</p>
  if (error) return <p className="text-destructive">{error}</p>
  if (!fn) return <p className="text-muted-foreground">Function not found</p>

  return (
    <div>
      {/* Header with back button, name, and action buttons */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/functions">
            <Button variant="ghost" size="sm">
              ← Back
            </Button>
          </Link>
          <h2 className="text-3xl font-bold">{fn.name}</h2>
          <Badge variant={fn.status === "active" ? "default" : "destructive"}>
            {fn.status}
          </Badge>
        </div>
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button variant="outline" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : "Save Changes"}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={startEditing}>
                Edit
              </Button>
              <Button variant="destructive" onClick={handleDelete}>
                Delete
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="space-y-6">
        {/* Function metadata */}
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            {editing ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-name">Name</Label>
                  <Input
                    id="edit-name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-desc">Description</Label>
                  <Input
                    id="edit-desc"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-2 text-sm">
                {fn.description && <p>{fn.description}</p>}
                <div className="flex gap-6 text-muted-foreground">
                  <span>Runtime: {fn.runtime}</span>
                  <span>Created: {new Date(fn.created_at).toLocaleString()}</span>
                  <span>Updated: {new Date(fn.updated_at).toLocaleString()}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Invoke URL - users can copy this to call the function */}
        <Card>
          <CardHeader>
            <CardTitle>Invoke URL</CardTitle>
          </CardHeader>
          <CardContent>
            <code className="block rounded bg-muted p-3 text-sm">
              POST {invokeUrl}
            </code>
            <p className="mt-2 text-xs text-muted-foreground">
              Send a POST request with a JSON body to invoke this function.
            </p>
          </CardContent>
        </Card>

        {/* Code viewer/editor */}
        <Card>
          <CardHeader>
            <CardTitle>Code</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-md border">
              <CodeEditor
                value={editing ? editCode : fn.code}
                onChange={editing ? setEditCode : undefined}
                readOnly={!editing}
              />
            </div>
          </CardContent>
        </Card>

        {/* Invocation logs placeholder - will show real data after Step 3 */}
        <Card>
          <CardHeader>
            <CardTitle>Invocation Logs</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No invocations yet. Logs will appear here once you invoke the
              function (available after the execution engine is built).
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
