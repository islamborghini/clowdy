/**
 * Sidebar navigation component.
 *
 * Renders a vertical sidebar with links to the main sections of the app.
 * Uses React Router's NavLink which automatically highlights the active route.
 */
import { NavLink } from "react-router"

// Define navigation items as data so we can loop over them.
// To add a new page, just add an entry here.
const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/functions", label: "Functions" },
]

export function Sidebar() {
  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      {/* App logo / brand */}
      <div className="flex h-14 items-center border-b px-4">
        <h1 className="text-xl font-bold">Clowdy</h1>
      </div>

      {/* Navigation links */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            // "end" ensures "/" only matches exactly "/", not "/functions" too.
            // Without this, the Dashboard link would be highlighted on every page.
            end={item.to === "/"}
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

      <div className="border-t p-4 text-xs text-muted-foreground">
        Clowdy v0.1.0
      </div>
    </aside>
  )
}
