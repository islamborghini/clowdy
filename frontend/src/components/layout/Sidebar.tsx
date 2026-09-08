/**
 * Sidebar navigation component.
 *
 * Renders a vertical sidebar with links to the main sections of the app.
 * Uses React Router's NavLink which automatically highlights the active route.
 * Shows the Clerk UserButton at the bottom for account management / sign out.
 */
import { NavLink } from "react-router"
import { UserButton } from "@clerk/clerk-react"
import { CLERK_ENABLED } from "@/components/auth/AuthProvider"

// Define navigation items as data so we can loop over them.
// To add a new page, just add an entry here.
const navItems = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/projects", label: "Projects" },
  { to: "/functions", label: "Functions" },
  { to: "/cluster", label: "Cluster" },
]

export function Sidebar() {
  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      {/* App logo / brand */}
      <div className="flex h-14 items-center border-b px-4">
        <NavLink to="/" className="text-xl font-bold">
          Clowdy
        </NavLink>
      </div>

      {/* Navigation links */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            // "end" ensures "/" only matches exactly "/", not "/functions" too.
            // Without this, the Dashboard link would be highlighted on every page.
            end={item.to === "/dashboard"}
            // NavLink gives us "isActive" - true when the current URL matches this link.
            // We use it to swap between highlighted and default styles.
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              }`
            }
          >
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* User account section. Clerk's UserButton throws without a
          ClerkProvider, so with auth switched off this renders a plain label
          instead of taking the whole app down. */}
      <div className="border-t p-4">
        {!CLERK_ENABLED ? (
          <p className="text-xs text-muted-foreground">Public demo - not signed in</p>
        ) : (
        <UserButton
          afterSignOutUrl="/sign-in"
          appearance={{
            elements: {
              rootBox: "w-full",
              userButtonTrigger: "w-full justify-start",
            },
          }}
        />
        )}
      </div>
    </aside>
  )
}
