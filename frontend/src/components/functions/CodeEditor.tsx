/**
 * Code editor component powered by Monaco Editor (the same editor used by VS Code).
 *
 * Wraps @monaco-editor/react with sensible defaults for writing Python functions.
 * Can be used in both editable and read-only modes.
 *
 * Props:
 *   value     - The code string to display
 *   onChange  - Called when the user edits the code (omit for read-only)
 *   readOnly  - If true, the editor is not editable
 *   language  - Syntax highlighting language (default: "python")
 *   height    - Editor height (default: "400px")
 */
import Editor from "@monaco-editor/react"

interface CodeEditorProps {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
  language?: string
  height?: string
}

export function CodeEditor({
  value,
  onChange,
  readOnly = false,
  language = "python",
  height = "400px",
}: CodeEditorProps) {
  return (
    <Editor
      height={height}
      language={language}
      value={value}
      onChange={(val) => onChange?.(val ?? "")}
      theme="vs-dark"
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: "on",
        scrollBeyondLastLine: false,
        wordWrap: "on",
        padding: { top: 12 },
      }}
    />
  )
}
