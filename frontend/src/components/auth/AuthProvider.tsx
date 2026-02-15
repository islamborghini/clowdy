/**
 * Clerk authentication provider.
 *
 * Wraps the app with ClerkProvider and injects the token getter into
 * the auth.ts module so that apiFetch can include the JWT in requests.
 *
 * Also provides an AuthGuard that redirects unauthenticated users to
 * the Clerk sign-in page.
 */
import { useEffect } from "react"
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
 */
function TokenInjector({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth()

  useEffect(() => {
    setTokenGetter(getToken)
  }, [getToken])

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
