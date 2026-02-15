/**
 * Root component of the Clowdy frontend.
 *
 * Sets up client-side routing using React Router. All pages are rendered
 * inside the Layout component, which provides the sidebar + main content area.
 *
 * Route structure:
 *   /                -> Dashboard (overview stats)
 *   /functions       -> List of all deployed functions
 *   /functions/new   -> Create a new function (code editor)
 *   /functions/:id   -> View/edit a specific function and its logs
 */
import { BrowserRouter, Routes, Route } from "react-router"
import { Layout } from "@/components/layout/Layout"
import { Dashboard } from "@/pages/Dashboard"
import { Functions } from "@/pages/Functions"
import { CreateFunction } from "@/pages/CreateFunction"
import { FunctionDetail } from "@/pages/FunctionDetail"

function App() {
  return (
    // BrowserRouter enables client-side routing (URL changes without full page reload)
    <BrowserRouter>
      <Routes>
        {/* Layout is a "layout route" - it wraps all child routes with the sidebar.
            The child page renders inside Layout's <Outlet /> component. */}
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/functions" element={<Functions />} />
          <Route path="/functions/new" element={<CreateFunction />} />
          {/* :id is a URL parameter - e.g. /functions/abc123 sets id="abc123" */}
          <Route path="/functions/:id" element={<FunctionDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
