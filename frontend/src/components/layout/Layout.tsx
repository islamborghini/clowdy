/**
 * Main layout wrapper used by all pages.
 *
 * Renders a two-column layout:
 *   - Left: fixed-width Sidebar with navigation links
 *   - Right: scrollable main content area where the current page renders
 *
 * Also includes the AI chat panel, accessible via a floating button
 * in the bottom-right corner. The chat panel slides in from the right.
 *
 * <Outlet /> is a React Router component that renders whichever child route
 * is currently active (Dashboard, Functions, etc.). Think of it as a placeholder
 * that says "put the current page here".
 */
import { useState } from "react"
import { Outlet } from "react-router"
import { Button } from "@/components/ui/button"
import { Sidebar } from "./Sidebar"
import { ChatPanel } from "@/components/chat/ChatPanel"

export function Layout() {
  const [chatOpen, setChatOpen] = useState(false)

  return (
    <div className="flex h-screen">
      <Sidebar />
      {/* flex-1 makes this take up all remaining horizontal space after the sidebar.
          overflow-auto adds a scrollbar if the page content is taller than the screen. */}
      <main className="flex-1 overflow-auto bg-background p-6">
        <Outlet />
      </main>

      {/* Floating chat button - bottom right corner */}
      {!chatOpen && (
        <Button
          onClick={() => setChatOpen(true)}
          className="fixed right-6 bottom-6 z-30 h-12 w-12 rounded-full shadow-lg"
          size="icon"
        >
          AI
        </Button>
      )}

      {/* Sliding chat panel */}
      <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  )
}
