/**
 * Auth token provider for API requests.
 *
 * The problem: apiFetch is a plain function, not a React component, so it
 * can't use hooks like useAuth(). But it needs the Clerk JWT token to send
 * in the Authorization header.
 *
 * The solution: this module acts as a bridge. A React component (AuthProvider)
 * calls setTokenGetter() once with Clerk's getToken function. Then apiFetch
 * calls getAuthToken() to get the current token for each request.
 */

type TokenGetter = () => Promise<string | null>

let _getToken: TokenGetter | null = null

/**
 * Set the function that retrieves the auth token.
 * Called once by AuthProvider when Clerk initializes.
 */
export function setTokenGetter(getter: TokenGetter) {
  _getToken = getter
}

/**
 * Get the current auth token (if available).
 * Returns null if the user is not signed in or Clerk isn't initialized yet.
 */
export async function getAuthToken(): Promise<string | null> {
  if (!_getToken) return null
  return _getToken()
}
