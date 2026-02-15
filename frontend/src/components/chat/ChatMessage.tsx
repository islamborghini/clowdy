/**
 * A single chat message bubble.
 *
 * User messages appear on the right with a primary background.
 * Assistant messages appear on the left with a muted background.
 * Tool calls (when the AI created/invoked a function) are shown as
 * small badges below the message text.
 */

interface ToolCall {
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
}

interface ChatMessageProps {
  role: "user" | "assistant"
  content: string
  toolCalls?: ToolCall[]
}

export function ChatMessage({ role, content, toolCalls }: ChatMessageProps) {
  const isUser = role === "user"

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        {/* Message text - preserve newlines */}
        <p className="whitespace-pre-wrap">{content}</p>

        {/* Show tool calls as small badges (only for assistant messages) */}
        {toolCalls && toolCalls.length > 0 && (
          <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
            {toolCalls.map((tc, i) => (
              <div key={i} className="text-xs opacity-75">
                <span className="font-mono font-medium">{tc.tool}</span>
                {tc.result && "success" in tc.result && (
                  <span className="ml-1">
                    {tc.result.success ? " - done" : " - failed"}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
