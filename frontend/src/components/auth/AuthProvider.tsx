/**
 * Clerk authentication provider.
 *
 * Wraps the app with ClerkProvider and injects the token getter into
 * the auth.ts module so that apiFetch can include the JWT in requests.
 *
 * Also provides an AuthGuard that redirects unauthenticated users to
 * the Clerk sign-in page.
 */
import { useEffect, useRef } from "react"
import {
  ClerkProvider,
  SignIn,
  SignUp,
  useAuth,
  SignedIn,
  SignedOut,
  RedirectToSignIn,
} from "@clerk/clerk-react"
import { setTokenGetter } from "@/lib/auth"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

/**
 * Inner component that bridges Clerk's useAuth hook with our auth.ts module.
 * Must be rendered inside ClerkProvider.
 *
 * Uses a ref to avoid stale closures: when Clerk finishes loading, the
 * getToken reference changes. A ref ensures the wrapper always calls the
 * latest version, even if child effects fire before this component's effect.
 */
function TokenInjector({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth()
  const getTokenRef = useRef(getToken)

  // Keep the ref current in an effect rather than during render. Mutating a
  // ref while rendering is not safe under StrictMode or concurrent rendering,
  // where a render can be thrown away and re-run.
  useEffect(() => {
    getTokenRef.current = getToken
  }, [getToken])

  // Registered once. Reading through the ref means apiFetch always calls
  // Clerk's latest getToken without this effect having to re-run.
  useEffect(() => {
    setTokenGetter(() => getTokenRef.current())
  }, [])

  return <>{children}</>
}

/**
 * Wraps children with Clerk authentication.
 * If VITE_CLERK_PUBLISHABLE_KEY is not set, renders children without auth
 * (allows running the app in dev without Clerk).
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (!CLERK_PUBLISHABLE_KEY) {
    return <>{children}</>
  }

  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
      <TokenInjector>{children}</TokenInjector>
    </ClerkProvider>
  )
}

/**
 * Guards a route so only signed-in users can access it.
 * Redirects to Clerk's sign-in page if not authenticated.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  if (!CLERK_PUBLISHABLE_KEY) {
    return <>{children}</>
  }

  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </>
  )
}

export { SignIn, SignUp }
