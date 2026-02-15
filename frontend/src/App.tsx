/**
 * Root component of the Clowdy frontend.
 *
 * Sets up client-side routing using React Router. All pages are rendered
 * inside the Layout component, which provides the sidebar + main content area.
 *
 * Authentication is handled by Clerk. The AuthProvider wraps the entire app
 * and the AuthGuard protects routes that require sign-in.
 *
 * Route structure:
 *   /sign-in         -> Clerk sign-in page
 *   /sign-up         -> Clerk sign-up page
 *   /                -> Dashboard (overview stats)
 *   /functions       -> List of all deployed functions
 *   /functions/new   -> Create a new function (code editor)
 *   /functions/:id   -> View/edit a specific function and its logs
 */
import { BrowserRouter, Routes, Route } from "react-router"
import { AuthProvider, AuthGuard, SignIn, SignUp } from "@/components/auth/AuthProvider"
import { Layout } from "@/components/layout/Layout"
import { Dashboard } from "@/pages/Dashboard"
import { Projects } from "@/pages/Projects"
import { CreateProject } from "@/pages/CreateProject"
import { ProjectDetail } from "@/pages/ProjectDetail"
import { Functions } from "@/pages/Functions"
import { CreateFunction } from "@/pages/CreateFunction"
import { FunctionDetail } from "@/pages/FunctionDetail"

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Auth routes - rendered outside the main layout */}
          <Route
            path="/sign-in/*"
            element={
              <div className="flex min-h-screen items-center justify-center">
                <SignIn routing="path" path="/sign-in" />
              </div>
            }
          />
          <Route
            path="/sign-up/*"
            element={
              <div className="flex min-h-screen items-center justify-center">
                <SignUp routing="path" path="/sign-up" />
              </div>
            }
          />

          {/* Protected routes - require authentication */}
          <Route
            element={
              <AuthGuard>
                <Layout />
              </AuthGuard>
            }
          >
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/new" element={<CreateProject />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/projects/:id/functions/new" element={<CreateFunction />} />
            <Route path="/functions" element={<Functions />} />
            <Route path="/functions/new" element={<CreateFunction />} />
            <Route path="/functions/:id" element={<FunctionDetail />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
