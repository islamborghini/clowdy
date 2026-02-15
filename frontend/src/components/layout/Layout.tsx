/**
 * Main layout wrapper used by all pages.
 *
 * Renders a two-column layout:
 *   - Left: fixed-width Sidebar with navigation links
 *   - Right: scrollable main content area where the current page renders
 *
 * <Outlet /> is a React Router component that renders whichever child route
 * is currently active (Dashboard, Functions, etc.). Think of it as a placeholder
 * that says "put the current page here".
 */
import { Outlet } from "react-router"
import { Sidebar } from "./Sidebar"

export function Layout() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      {/* flex-1 makes this take up all remaining horizontal space after the sidebar.
          overflow-auto adds a scrollbar if the page content is taller than the screen. */}
      <main className="flex-1 overflow-auto bg-background p-6">
        <Outlet />
      </main>
    </div>
  )
}
