/**
 * Sliding chat panel for talking to the AI agent.
 *
 * Opens from the right side of the screen. The user types a message,
 * it's sent to POST /api/chat along with the full conversation history,
 * and the AI's response (with any tool call results) is displayed.
 *
 * The conversation history is kept in state so the AI has context of
 * previous messages (it can reference earlier functions, etc.).
 */
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ChatMessage } from "./ChatMessage"
import { api, type ChatMessage as ChatMessageType } from "@/lib/api"

interface ToolCall {
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
}

/** A message in the UI - extends ChatMessage with optional tool call data. */
interface UIMessage {
  role: "user" | "assistant"
  content: string
  toolCalls?: ToolCall[]
}

interface ChatPanelProps {
  open: boolean
  onClose: () => void
}

export function ChatPanel({ open, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to the bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  /** Send the user's message to the AI agent. */
  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    // Add user message to the UI
    const userMessage: UIMessage = { role: "user", content: text }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput("")
    setLoading(true)

    try {
      // Send full conversation history to the backend (minus tool call data,
      // which is UI-only). The backend needs role + content for Groq.
      const apiMessages: ChatMessageType[] = updatedMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }))

      const result = await api.chat(apiMessages)

      // Add the AI's response to the UI
      const assistantMessage: UIMessage = {
        role: "assistant",
        content: result.response,
        toolCalls: result.tool_calls,
      }
      setMessages([...updatedMessages, assistantMessage])
    } catch (err) {
      // Show error as an assistant message so the user can see it
      const errorMessage: UIMessage = {
        role: "assistant",
        content:
          err instanceof Error
            ? `Error: ${err.message}`
            : "Something went wrong. Is the backend running?",
      }
      setMessages([...updatedMessages, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  /** Handle Enter key to send message. */
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <>
      {/* Backdrop - click to close */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/20"
          onClick={onClose}
        />
      )}

      {/* Sliding panel */}
      <div
        className={`fixed top-0 right-0 z-50 flex h-full w-96 flex-col border-l bg-background shadow-lg transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="font-semibold">AI Assistant</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            X
          </Button>
        </div>

        {/* Messages area */}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <p className="mb-2 font-medium">How can I help?</p>
              <p>Try: &quot;Create a function that adds two numbers&quot;</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatMessage
              key={i}
              role={msg.role}
              content={msg.content}
              toolCalls={msg.toolCalls}
            />
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="border-t p-3">
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask the AI..."
              disabled={loading}
              className="flex-1"
            />
            <Button onClick={handleSend} disabled={loading || !input.trim()}>
              Send
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
