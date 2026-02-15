/**
 * Function Detail page.
 *
 * Displays a single function's metadata, source code (in a Monaco editor),
 * and its invoke URL. Supports editing the code, deleting the function,
 * testing the function with a JSON input, and viewing invocation logs.
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
import {
  api,
  type FunctionResponse,
  type InvocationResponse,
} from "@/lib/api"

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

  // Invoke/test state
  const [testInput, setTestInput] = useState("{}")
  const [invoking, setInvoking] = useState(false)
  const [invokeResult, setInvokeResult] = useState<string | null>(null)
  const [invokeError, setInvokeError] = useState("")

  // Invocation logs state
  const [invocations, setInvocations] = useState<InvocationResponse[]>([])
  const [logsLoading, setLogsLoading] = useState(false)

  // The URL users will call to invoke this function
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

  // Fetch invocation logs on mount and after each invocation
  function loadInvocations() {
    if (!id) return
    setLogsLoading(true)
    api.functions
      .invocations(id)
      .then(setInvocations)
      .catch(() => {})
      .finally(() => setLogsLoading(false))
  }

  useEffect(() => {
    loadInvocations()
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

  /** Invoke the function with the test input JSON. */
  async function handleInvoke() {
    if (!id) return
    setInvoking(true)
    setInvokeResult(null)
    setInvokeError("")

    // Parse the test input - must be valid JSON
    let parsedInput: Record<string, unknown>
    try {
      parsedInput = JSON.parse(testInput)
    } catch {
      setInvokeError("Invalid JSON input")
      setInvoking(false)
      return
    }

    try {
      const result = await api.functions.invoke(id, parsedInput)
      if (result.success) {
        setInvokeResult(JSON.stringify(result.output, null, 2))
      } else {
        setInvokeError(result.error || "Function returned an error")
      }
      // Refresh the invocation logs after running
      loadInvocations()
    } catch (err) {
      setInvokeError(err instanceof Error ? err.message : "Failed to invoke")
    } finally {
      setInvoking(false)
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

        {/* Invoke URL and test panel */}
        <Card>
          <CardHeader>
            <CardTitle>Invoke</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <code className="block rounded bg-muted p-3 text-sm">
                POST {invokeUrl}
              </code>
              <p className="mt-2 text-xs text-muted-foreground">
                Send a POST request with a JSON body to invoke this function.
              </p>
            </div>

            {/* Test panel - type JSON input and run the function */}
            <div className="space-y-2">
              <Label htmlFor="test-input">Test Input (JSON)</Label>
              <Input
                id="test-input"
                value={testInput}
                onChange={(e) => setTestInput(e.target.value)}
                placeholder='{"name": "World"}'
                className="font-mono text-sm"
              />
              <Button
                onClick={handleInvoke}
                disabled={invoking}
                size="sm"
              >
                {invoking ? "Running..." : "Run Function"}
              </Button>
            </div>

            {/* Show invoke result or error */}
            {invokeResult && (
              <div className="space-y-1">
                <p className="text-sm font-medium">Result:</p>
                <pre className="rounded bg-muted p-3 text-sm whitespace-pre-wrap">
                  {invokeResult}
                </pre>
              </div>
            )}
            {invokeError && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-destructive">Error:</p>
                <pre className="rounded bg-destructive/10 p-3 text-sm text-destructive whitespace-pre-wrap">
                  {invokeError}
                </pre>
              </div>
            )}
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

        {/* Invocation logs - real data from the backend */}
        <Card>
          <CardHeader>
            <CardTitle>Invocation Logs</CardTitle>
          </CardHeader>
          <CardContent>
            {logsLoading ? (
              <p className="text-sm text-muted-foreground">Loading logs...</p>
            ) : invocations.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No invocations yet. Use the test panel above or send a POST
                request to the invoke URL.
              </p>
            ) : (
              <div className="space-y-3">
                {invocations.map((inv) => (
                  <div
                    key={inv.id}
                    className="rounded border p-3 text-sm"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            inv.status === "success" ? "default" : "destructive"
                          }
                        >
                          {inv.status}
                        </Badge>
                        <span className="text-muted-foreground">
                          {inv.duration_ms}ms
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(inv.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      <div>
                        <p className="mb-1 text-xs font-medium text-muted-foreground">
                          Input
                        </p>
                        <pre className="rounded bg-muted p-2 text-xs whitespace-pre-wrap">
                          {formatJson(inv.input)}
                        </pre>
                      </div>
                      <div>
                        <p className="mb-1 text-xs font-medium text-muted-foreground">
                          Output
                        </p>
                        <pre className="rounded bg-muted p-2 text-xs whitespace-pre-wrap">
                          {formatJson(inv.output)}
                        </pre>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/** Pretty-print a JSON string. If it's not valid JSON, return as-is. */
function formatJson(str: string): string {
  try {
    return JSON.stringify(JSON.parse(str), null, 2)
  } catch {
    return str
  }
}
